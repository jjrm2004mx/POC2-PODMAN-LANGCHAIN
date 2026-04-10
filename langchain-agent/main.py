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
    conversation_id: Optional[str] = None   # ID del hilo Outlook — deduplicación
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
# TAREA EN BACKGROUND
# =============================================================================

async def process_email_job(job_id: str, request: ProcessRequest):
    """
    Ejecuta la clasificación del correo en background.
    Actualiza el estado en Redis al completar o en caso de error.
    """
    start_time = time.time()
    run_id = job_id

    # ─── DEDUPLICACIÓN: enriquecer si ya existe un ticket para este hilo ──────
    if request.conversation_id:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow(
                    "SELECT id, external_ticket_id, asunto, dominio, categoria "
                    "FROM ss_tickets WHERE conversation_id = $1",
                    request.conversation_id,
                )
            finally:
                await conn.close()

            if row:
                ticket_id_local    = row["id"]
                external_ticket_id = row["external_ticket_id"]
                print(
                    f"[DEDUP] conversation_id={request.conversation_id} "
                    f"ya tiene ticket_id={ticket_id_local} — evaluando enriquecimiento",
                    flush=True,
                )

                enrich_result = {"relevante": False, "razon": "sin external_ticket_id", "comment_id": None, "adjuntos_agregados": 0}
                if external_ticket_id:
                    enrich_result = await enrich_ticket(
                        external_ticket_id=external_ticket_id,
                        ticket_id_local=ticket_id_local,
                        ticket_asunto_original=row["asunto"] or "",
                        ticket_dominio=row["dominio"] or "",
                        ticket_categoria=row["categoria"] or "",
                        asunto=request.asunto,
                        cuerpo=request.cuerpo,
                        remitente=request.remitente,
                        nombre_remitente=request.nombre_remitente,
                        adjuntos=[adj.dict() for adj in (request.adjuntos or [])],
                        provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
                    )

                # Auditoría local en ss_enrichments
                try:
                    conn = await asyncpg.connect(DATABASE_URL)
                    try:
                        await conn.execute(
                            """INSERT INTO ss_enrichments
                               (ticket_id, conversation_id, remitente, nombre_remitente,
                                relevante, razon, comment_id, adjuntos_agregados)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                            ticket_id_local,
                            request.conversation_id,
                            request.remitente,
                            request.nombre_remitente,
                            enrich_result["relevante"],
                            enrich_result.get("razon"),
                            enrich_result.get("comment_id"),
                            enrich_result.get("adjuntos_agregados", 0),
                        )
                    finally:
                        await conn.close()
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
                        "conversation_id":     request.conversation_id,
                        "comment_id":          enrich_result.get("comment_id"),
                        "adjuntos_agregados":  enrich_result.get("adjuntos_agregados", 0),
                    }),
                )
                return
        except Exception as e:
            print(f"[WARN DEDUP] Error verificando conversation_id: {e}", flush=True)

    try:
        initial_state = AgentState(
            asunto=request.asunto,
            cuerpo=request.cuerpo,
            origen="webhook",
            remitente=request.remitente,
            nombre_remitente=request.nombre_remitente,
            conversation_id=request.conversation_id,
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
