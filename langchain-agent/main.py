import os
import time
import uuid
import json
import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from prometheus_fastapi_instrumentator import Instrumentator

from agent import agent, AgentState, MAX_ITERATIONS, AGENT_DOMAINS, DATABASE_URL

app = FastAPI(
    title="shared-services-classifier — Agent",
    description="Clasificador de tickets LangGraph. POST /process para clasificar.",
    version="1.0.0",
)

Instrumentator().instrument(app).expose(app)

class ProcessRequest(BaseModel):
    texto: str
    origen: str = "webhook"
    remitente: Optional[str] = None
    provider: Optional[str] = None
    max_iterations: Optional[int] = None

class ProcessResponse(BaseModel):
    run_id: str
    dominio: Optional[str] = None
    categoria: Optional[str] = None
    categoria_propuesta: Optional[str] = None
    requiere_revision: bool = False
    prioridad: Optional[str] = None
    confianza: Optional[float] = None
    alerta: Optional[str] = None
    ticket_id: Optional[int] = None
    texto_original: str
    origen: str
    remitente: Optional[str] = None
    iterations_used: int
    validated: bool
    cached: bool = False
    error: Optional[str] = None

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

@app.post("/process", response_model=ProcessResponse)
async def process_ticket(request: ProcessRequest):
    run_id = str(uuid.uuid4())
    start_time = time.time()

    initial_state = AgentState(
        texto=request.texto,
        origen=request.origen,
        remitente=request.remitente,
        provider=request.provider or os.getenv("AGENT_PROVIDER", "ollama"),
        max_iterations=request.max_iterations or MAX_ITERATIONS,
    )

    try:
        final_state = await agent.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el agente: {str(e)}")

    duracion_ms = int((time.time() - start_time) * 1000)

    # LangGraph devuelve dict — acceder con .get(), nunca con atributos
    validated      = final_state.get("validated", False)
    iterations_used = final_state.get("iterations", 0)
    classification = final_state.get("classification")
    last_error     = final_state.get("error")
    cached         = final_state.get("cached", False)

    # Persistir en ss_agent_runs — errores visibles en logs
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute(
                """INSERT INTO ss_agent_runs
                   (run_id, ticket_id, iterations_used, validated,
                    provider_usado, resultado, duracion_ms)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)""",
                run_id,
                classification.get("ticket_id") if classification else None,
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

    if not validated:
        return ProcessResponse(
            run_id=run_id,
            texto_original=request.texto,
            origen=request.origen,
            remitente=request.remitente,
            iterations_used=iterations_used,
            validated=False,
            error=last_error or "Máximo de iteraciones alcanzado sin clasificación válida",
        )

    return ProcessResponse(
        run_id=run_id,
        dominio=classification.get("dominio"),
        categoria=classification.get("categoria"),
        categoria_propuesta=classification.get("categoria_propuesta"),
        requiere_revision=classification.get("requiere_revision", False),
        prioridad=classification.get("prioridad"),
        confianza=classification.get("confianza"),
        alerta=classification.get("alerta"),
        ticket_id=classification.get("ticket_id"),
        texto_original=request.texto,
        origen=request.origen,
        remitente=request.remitente,
        iterations_used=iterations_used,
        validated=True,
        cached=cached,
    )
