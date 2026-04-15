import os
import time
import uuid
import json
import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from prometheus_fastapi_instrumentator import Instrumentator

from agent import agent, AgentState, MAX_ITERATIONS, AGENT_DOMAINS, DATABASE_URL, enrich_ticket
from db.queries import get_ticket_by_email_id, get_ticket_by_thread_id, get_ticket_by_references, insert_enrichment

app = FastAPI(
    title="shared-services-classifier — Agent",
    description="Clasificador de tickets LangGraph. POST /process para clasificar.",
    version="2.0.0",
)

Instrumentator().instrument(app).expose(app)

# =============================================================================
# CLIENTES EXTERNOS
# =============================================================================

redis_client = aioredis.from_url(
    f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}",
    decode_responses=True,
)

JOB_TTL_SECONDS = 86400  # 24 horas

# =============================================================================
# MODELOS DE ENTRADA / SALIDA
# =============================================================================

class AdjuntoInfo(BaseModel):
    nombre: str
    tipo: Optional[str] = None          # MIME type (e.g. application/vnd.ms-excel)
    contenido_b64: Optional[str] = None # Contenido del archivo en base64

class ProcessRequest(BaseModel):
    asunto: str
    cuerpo: str
    remitente: Optional[str] = None
    nombre_remitente: Optional[str] = None
    conversation_id: Optional[str] = None   # SMTP Message-ID — solo auditoría
    id: Optional[str] = None                # Gmail message ID — deduplicación
    threadId: Optional[str] = None          # Gmail thread ID — detección de reply
    references: Optional[str] = None        # Gmail references header — detección de FW (string o JSON array)
    to: Optional[str] = None                # Destinatario(s) directo(s) del correo
    fecha_correo: Optional[str] = None      # Fecha ISO del correo
    origen: Optional[str] = None            # Proveedor: gmail, outlook, etc.
    adjuntos: Optional[List[AdjuntoInfo]] = []
    provider: Optional[str] = None
    max_iterations: Optional[int] = None

class JobAcceptedResponse(BaseModel):
    job_id: str
    status: str = "en_proceso"

class JobStatusResponse(BaseModel):
    job_id: str
    status: str                          # en_proceso | completado | error | ignorado
    asunto: Optional[str] = None
    remitente: Optional[str] = None
    nombre_remitente: Optional[str] = None
    conversation_id: Optional[str] = None
    ticket_id: Optional[int] = None
    ticket_id_existente: Optional[int] = None  # Solo en status=ignorado / enriquecido
    motivo: Optional[str] = None               # Solo en status=ignorado / enriquecido
    comment_id: Optional[str] = None           # Solo en status=enriquecido
    adjuntos_agregados: Optional[int] = None   # Solo en status=enriquecido
    external_ticket_id: Optional[str] = None   # UUID en ticket-management-backend
    dominio: Optional[str] = None
    categoria: Optional[str] = None
    categoria_propuesta: Optional[str] = None
    requiere_revision: bool = False
    prioridad: Optional[str] = None
    confianza: Optional[float] = None
    alerta: Optional[str] = None
    iterations_used: Optional[int] = None
    validated: Optional[bool] = None
    cached: Optional[bool] = None
    provider: Optional[str] = None
    duracion_ms: Optional[int] = None
    error: Optional[str] = None

# =============================================================================
# HELPERS — DEDUP
# =============================================================================

SS_EMAIL = os.getenv("SS_EMAIL", "").lower()


def parse_references(raw) -> List[str]:
    """Normaliza el campo references a List[str].
    n8n puede enviar: null | "<id>" | "[\"<id1>\",\"<id2>\"]"
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [r for r in raw if r]
    s = raw.strip()
    if s.startswith("["):
        try:
            return [r for r in json.loads(s) if r]
        except (json.JSONDecodeError, ValueError):
            pass
    return [s] if s else []


def is_ss_direct_recipient(to: Optional[str]) -> bool:
    """Devuelve True si SS_EMAIL está en el campo To (destinatario directo de la acción).
    Si SS está solo en CC → False (solo informado, sin acción requerida).
    Si SS_EMAIL no está configurado → se asume directo.
    """
    if not SS_EMAIL:
        return True
    return SS_EMAIL in (to or "").lower()


# =============================================================================
# TAREA EN BACKGROUND
# =============================================================================

async def process_email_job(job_id: str, request: ProcessRequest):
    """
    Ejecuta la clasificación del correo en background.
    Actualiza el estado en Redis al completar o en caso de error.
    """
    start_time = time.time()
    run_id = job_id

    # ─── CLASIFICACIÓN DE TIPO: duplicado / reply / nuevo ────────────────────
    email_type = "nuevo"
    dedup_row  = None

    try:
        if request.id:
            dedup_row = await get_ticket_by_email_id(request.id)
            if dedup_row:
                email_type = "duplicado"

        if email_type == "nuevo" and request.threadId:
            dedup_row = await get_ticket_by_thread_id(request.threadId)
            if dedup_row:
                email_type = "reply"

        # ── FW: hilo roto con referencias conocidas o prefijo de reenvío (solo Gmail) ──
        if email_type == "nuevo" and request.origen == "gmail":
            refs = parse_references(request.references)
            _fw_prefixes = ("fw:", "fwd:", "rv:", "re:", "fw ", "rv ", "fwd ")
            has_fw_prefix = (request.asunto or "").lower().startswith(_fw_prefixes)
            ss_directo    = is_ss_direct_recipient(request.to)

            if refs:
                # FW con referencias — buscar ticket vinculado en DB
                dedup_row = await get_ticket_by_references(refs)
                if dedup_row:
                    email_type = "forward_linked" if ss_directo else "forward_cc"
            elif has_fw_prefix and not ss_directo:
                # FW sin referencias pero SS solo en CC → conversación usuario-a-usuario
                email_type = "forward_cc"

        if email_type == "duplicado":
            dedup_reason = f"email_id={request.id} ya existe en ss_tickets (ticket_id={dedup_row['id']})"
        elif email_type == "reply":
            dedup_reason = f"threadId={request.threadId} ya tiene ticket_id={dedup_row['id']} → se enriquecerá"
        elif email_type == "forward_linked":
            dedup_reason = f"references vinculan a ticket_id={dedup_row['id']} y SS es destinatario directo → evaluando enriquecimiento"
        elif email_type == "forward_cc" and dedup_row:
            dedup_reason = f"references vinculan a ticket_id={dedup_row['id']} pero SS solo está en CC → ignorado"
        elif email_type == "forward_cc":
            dedup_reason = f"prefijo FW/RV en asunto y SS solo en CC → conversación usuario-a-usuario, ignorado"
        else:
            dedup_reason = "sin match en ss_tickets → correo nuevo"
        print(
            f"[DEDUP] email_type={email_type} | "
            f"id={request.id} | threadId={request.threadId} | "
            f"razon={dedup_reason}",
            flush=True,
        )
    except Exception as e:
        print(f"[WARN DEDUP] Error clasificando tipo de correo: {e}", flush=True)

    # ─── DUPLICADO: el mensaje ya fue procesado ───────────────────────────────
    if email_type == "duplicado":
        await redis_client.setex(
            f"job:{job_id}",
            JOB_TTL_SECONDS,
            json.dumps({
                "status":              "duplicado",
                "motivo":              "email_id ya existe en el sistema",
                "ticket_id_existente": dedup_row["id"],
                "external_ticket_id":  dedup_row["external_ticket_id"],
                "email_id":            request.id,
                "thread_id":           request.threadId,
                "conversation_id":     request.conversation_id,
            }),
        )
        return

    # ─── REPLY: nuevo mensaje en un hilo ya conocido → enriquecer ────────────
    if email_type == "reply":
        ticket_id_local    = dedup_row["id"]
        external_ticket_id = dedup_row["external_ticket_id"]
        print(
            f"[DEDUP] thread_id={request.threadId} "
            f"ya tiene ticket_id={ticket_id_local} — evaluando enriquecimiento",
            flush=True,
        )

        enrich_result = {"relevante": False, "razon": "sin external_ticket_id", "comment_id": None, "adjuntos_agregados": 0}
        if external_ticket_id:
            enrich_result = await enrich_ticket(
                external_ticket_id=external_ticket_id,
                ticket_id_local=ticket_id_local,
                ticket_asunto_original=dedup_row["asunto"] or "",
                ticket_dominio=dedup_row["dominio"] or "",
                ticket_categoria=dedup_row["categoria"] or "",
                asunto=request.asunto,
                cuerpo=request.cuerpo,
                remitente=request.remitente,
                nombre_remitente=request.nombre_remitente,
                adjuntos=[adj.dict() for adj in (request.adjuntos or [])],
                provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
            )

        try:
            await insert_enrichment(
                ticket_id=ticket_id_local,
                conversation_id=request.conversation_id,
                email_id=request.id,
                thread_id=request.threadId,
                remitente=request.remitente,
                nombre_remitente=request.nombre_remitente,
                relevante=enrich_result["relevante"],
                razon=enrich_result.get("razon"),
                comment_id=enrich_result.get("comment_id"),
                adjuntos_agregados=enrich_result.get("adjuntos_agregados", 0),
            )
        except Exception as e:
            print(f"[WARN ss_enrichments] {e}", flush=True)

        status = "enriquecido" if enrich_result["relevante"] else "ignorado"
        motivo = enrich_result.get("razon") or "respuesta a cadena existente sin información nueva"
        await redis_client.setex(
            f"job:{job_id}",
            JOB_TTL_SECONDS,
            json.dumps({
                "status":              status,
                "motivo":              motivo,
                "ticket_id_existente": ticket_id_local,
                "external_ticket_id":  external_ticket_id,
                "email_id":            request.id,
                "thread_id":           request.threadId,
                "conversation_id":     request.conversation_id,
                "comment_id":          enrich_result.get("comment_id"),
                "adjuntos_agregados":  enrich_result.get("adjuntos_agregados", 0),
            }),
        )
        return

    # ─── FORWARD_CC: SS solo en copia → sin acción ───────────────────────────
    if email_type == "forward_cc":
        await redis_client.setex(
            f"job:{job_id}",
            JOB_TTL_SECONDS,
            json.dumps({
                "status":              "ignorado",
                "motivo":              "FW con SS en CC — no requiere acción",
                "ticket_id_existente": dedup_row["id"],
                "external_ticket_id":  dedup_row["external_ticket_id"],
                "email_id":            request.id,
                "thread_id":           request.threadId,
                "conversation_id":     request.conversation_id,
            }),
        )
        return

    # ─── FORWARD_LINKED: FW con SS como destinatario directo → enriquecer ────
    if email_type == "forward_linked":
        ticket_id_local    = dedup_row["id"]
        external_ticket_id = dedup_row["external_ticket_id"]
        print(
            f"[DEDUP] forward_linked → ticket_id={ticket_id_local} — evaluando enriquecimiento",
            flush=True,
        )

        enrich_result = {"relevante": False, "razon": "sin external_ticket_id", "comment_id": None, "adjuntos_agregados": 0}
        if external_ticket_id:
            enrich_result = await enrich_ticket(
                external_ticket_id=external_ticket_id,
                ticket_id_local=ticket_id_local,
                ticket_asunto_original=dedup_row["asunto"] or "",
                ticket_dominio=dedup_row["dominio"] or "",
                ticket_categoria=dedup_row["categoria"] or "",
                asunto=request.asunto,
                cuerpo=request.cuerpo,
                remitente=request.remitente,
                nombre_remitente=request.nombre_remitente,
                adjuntos=[adj.dict() for adj in (request.adjuntos or [])],
                provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
            )

        try:
            await insert_enrichment(
                ticket_id=ticket_id_local,
                conversation_id=request.conversation_id,
                email_id=request.id,
                thread_id=request.threadId,
                remitente=request.remitente,
                nombre_remitente=request.nombre_remitente,
                relevante=enrich_result["relevante"],
                razon=enrich_result.get("razon"),
                comment_id=enrich_result.get("comment_id"),
                adjuntos_agregados=enrich_result.get("adjuntos_agregados", 0),
            )
        except Exception as e:
            print(f"[WARN ss_enrichments] {e}", flush=True)

        status = "enriquecido" if enrich_result["relevante"] else "ignorado"
        motivo = enrich_result.get("razon") or "FW sin información nueva para el ticket"
        await redis_client.setex(
            f"job:{job_id}",
            JOB_TTL_SECONDS,
            json.dumps({
                "status":              status,
                "motivo":              motivo,
                "ticket_id_existente": ticket_id_local,
                "external_ticket_id":  external_ticket_id,
                "email_id":            request.id,
                "thread_id":           request.threadId,
                "conversation_id":     request.conversation_id,
                "comment_id":          enrich_result.get("comment_id"),
                "adjuntos_agregados":  enrich_result.get("adjuntos_agregados", 0),
            }),
        )
        return

    try:
        initial_state = AgentState(
            asunto=request.asunto,
            cuerpo=request.cuerpo,
            origen=request.origen or "webhook",
            remitente=request.remitente,
            nombre_remitente=request.nombre_remitente,
            conversation_id=request.conversation_id,
            email_id=request.id,
            thread_id=request.threadId,
            fecha_correo=request.fecha_correo,
            email_type=email_type,
            provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
            max_iterations=request.max_iterations or MAX_ITERATIONS,
            adjuntos=[adj.dict() for adj in (request.adjuntos or [])],
        )

        final_state = await agent.ainvoke(initial_state)

        validated       = final_state.get("validated", False)
        iterations_used = final_state.get("iterations", 0)
        classification  = final_state.get("classification")
        last_error      = final_state.get("error")
        cached          = final_state.get("cached", False)
        ticket_id       = classification.get("ticket_id") if classification else None

        # Guardar metadata de adjuntos en ss_adjuntos (sin contenido)
        if ticket_id and request.adjuntos:
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                for adj in request.adjuntos:
                    await conn.execute(
                        """INSERT INTO ss_adjuntos (ticket_id, nombre, tipo_mime)
                           VALUES ($1, $2, $3)""",
                        ticket_id, adj.nombre, adj.tipo,
                    )
            finally:
                await conn.close()

        # Persistir ejecución en ss_agent_runs
        duracion_ms = int((time.time() - start_time) * 1000)
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute(
                    """INSERT INTO ss_agent_runs
                       (run_id, ticket_id, iterations_used, validated,
                        provider_usado, resultado, duracion_ms)
                       VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)""",
                    run_id,
                    ticket_id,
                    iterations_used,
                    validated,
                    initial_state.provider,
                    json.dumps(classification) if classification else None,
                    duracion_ms,
                )
            finally:
                await conn.close()
        except Exception as e:
            print(f"[ERROR ss_agent_runs] {e}", flush=True)

        # Actualizar Redis con resultado final
        result = {
            "status": "completado",
            "asunto": request.asunto,
            "remitente": request.remitente,
            "nombre_remitente": request.nombre_remitente,
            "conversation_id": request.conversation_id,
            "ticket_id": ticket_id,
            "external_ticket_id": classification.get("external_ticket_id") if classification else None,
            "dominio": classification.get("dominio") if classification else None,
            "categoria": classification.get("categoria") if classification else None,
            "categoria_propuesta": classification.get("categoria_propuesta") if classification else None,
            "requiere_revision": classification.get("requiere_revision", False) if classification else False,
            "prioridad": classification.get("prioridad") if classification else None,
            "confianza": classification.get("confianza") if classification else None,
            "alerta": classification.get("alerta") if classification else None,
            "iterations_used": iterations_used,
            "validated": validated,
            "cached": cached,
            "provider": initial_state.provider,
            "duracion_ms": duracion_ms,
            "error": last_error,
        }

    except Exception as e:
        print(f"[ERROR process_email_job] job_id={job_id} — {e}", flush=True)
        result = {
            "status": "error",
            "asunto": request.asunto,
            "remitente": request.remitente,
            "nombre_remitente": request.nombre_remitente,
            "error": str(e),
        }

    await redis_client.setex(f"job:{job_id}", JOB_TTL_SECONDS, json.dumps(result))

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "langchain-agent",
        "agent_provider": os.getenv("AGENT_PROVIDER", "ollama"),
        "agent_domains": AGENT_DOMAINS,
        "max_iterations": MAX_ITERATIONS,
        "validation_enabled": os.getenv("VALIDATION_ENABLED", "true"),
    }

@app.post("/process", status_code=202, response_model=JobAcceptedResponse)
async def process_ticket(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Recibe un correo desde Power Automate y lo encola para clasificación.
    Devuelve un job_id inmediatamente (202 Accepted).
    Consultar el resultado en GET /status/{job_id}.
    """
    job_id = str(uuid.uuid4())

    # Registrar estado inicial en Redis antes de encolar
    await redis_client.setex(
        f"job:{job_id}",
        JOB_TTL_SECONDS,
        json.dumps({
            "status": "en_proceso",
            "asunto": request.asunto,
            "remitente": request.remitente,
        }),
    )

    background_tasks.add_task(process_email_job, job_id, request)

    return JobAcceptedResponse(job_id=job_id)

@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Consulta el estado de un job de clasificación.
    Power Automate hace polling a este endpoint hasta obtener status=completado|error.
    """
    data = await redis_client.get(f"job:{job_id}")
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"job_id '{job_id}' no encontrado o expirado (TTL 24h)",
        )

    result = json.loads(data)
    return JobStatusResponse(job_id=job_id, **result)
