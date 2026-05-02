import os
import time
import uuid
import json
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from prometheus_fastapi_instrumentator import Instrumentator

from agent import agent, AgentState, MAX_ITERATIONS, AGENT_DOMAINS
from db.engine import AsyncSessionLocal
from db.queries import get_ticket_by_conversation_id, insert_attachment, insert_agent_run

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
    email_received_at: Optional[str] = None
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
    ticket_id_existente: Optional[int] = None  # Solo en status=ignorado
    motivo: Optional[str] = None               # Solo en status=ignorado
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

    # ─── DEDUPLICACIÓN: ignorar si ya existe un ticket para este hilo ─────────
    if request.conversation_id:
        try:
            async with AsyncSessionLocal() as session:
                ticket_existente = await get_ticket_by_conversation_id(
                    session, request.conversation_id
                )

            if ticket_existente:
                print(
                    f"[DEDUP] conversation_id={request.conversation_id} "
                    f"ya tiene ticket_id={ticket_existente} — ignorando",
                    flush=True,
                )
                await redis_client.setex(
                    f"job:{job_id}",
                    JOB_TTL_SECONDS,
                    json.dumps({
                        "status": "ignorado",
                        "motivo": "respuesta a cadena existente",
                        "ticket_id_existente": ticket_existente,
                        "conversation_id": request.conversation_id,
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
            email_received_at=request.email_received_at,
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

        # Guardar metadata de adjuntos en attachments (sin contenido)
        if ticket_id and request.adjuntos:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for adj in request.adjuntos:
                        await insert_attachment(session, ticket_id, adj.nombre, adj.tipo)

        # Persistir ejecución en agent_runs
        duracion_ms = int((time.time() - start_time) * 1000)
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await insert_agent_run(
                        session,
                        run_id=run_id,
                        ticket_id=ticket_id,
                        iterations_used=iterations_used,
                        is_validated=validated,
                        provider=initial_state.provider,
                        result=classification,
                        duration_ms=duracion_ms,
                    )
        except Exception as e:
            print(f"[ERROR agent_runs] {e}", flush=True)

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
