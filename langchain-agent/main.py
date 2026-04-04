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

from agent import agent, AgentState, MAX_ITERATIONS, AGENT_DOMAINS, DATABASE_URL

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

class ProcessRequest(BaseModel):
    asunto: str
    cuerpo: str
    remitente: Optional[str] = None
    adjuntos: Optional[List[AdjuntoInfo]] = []
    provider: Optional[str] = None
    max_iterations: Optional[int] = None

class JobAcceptedResponse(BaseModel):
    job_id: str
    status: str = "en_proceso"

class JobStatusResponse(BaseModel):
    job_id: str
    status: str                          # en_proceso | completado | error
    asunto: Optional[str] = None
    remitente: Optional[str] = None
    ticket_id: Optional[int] = None
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

    try:
        initial_state = AgentState(
            asunto=request.asunto,
            cuerpo=request.cuerpo,
            origen="webhook",
            remitente=request.remitente,
            provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
            max_iterations=request.max_iterations or MAX_ITERATIONS,
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
            "ticket_id": ticket_id,
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
            "error": last_error,
        }

    except Exception as e:
        print(f"[ERROR process_email_job] job_id={job_id} — {e}", flush=True)
        result = {
            "status": "error",
            "asunto": request.asunto,
            "remitente": request.remitente,
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
