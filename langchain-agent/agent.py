# =============================================================================
# langchain-agent/agent.py
# Grafo LangGraph: classify → validate → save
# =============================================================================

import os
import json
import httpx
import asyncpg
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, validator
from typing import Optional

AGENT_DOMAINS = os.getenv("AGENT_DOMAINS", "IT,cliente,operaciones,otro").split(",")
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
LANGCHAIN_API_URL = os.getenv("LANGCHAIN_API_URL", "http://langchain-api:8000")
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'admin')}"
    f":{os.getenv('POSTGRES_PASSWORD', 'admin')}"
    f"@{os.getenv('POSTGRES_HOST', 'postgres')}"
    f":{os.getenv('POSTGRES_PORT', '5432')}"
    f"/{os.getenv('POSTGRES_DB', 'ai')}"
)

class ClasificacionSchema(BaseModel):
    dominio: str
    categoria: str
    prioridad: str
    confianza: float

    @validator("dominio")
    def dominio_valido(cls, v):
        if v not in AGENT_DOMAINS:
            raise ValueError(f"dominio '{v}' no está en {AGENT_DOMAINS}")
        return v

    @validator("prioridad")
    def prioridad_valida(cls, v):
        if v not in ["alta", "media", "baja"]:
            raise ValueError(f"prioridad '{v}' debe ser: alta | media | baja")
        return v

    @validator("confianza")
    def confianza_valida(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confianza {v} debe estar entre 0.0 y 1.0")
        return v

class AgentState(BaseModel):
    texto: str
    origen: str = "webhook"
    remitente: Optional[str] = None
    provider: str = "ollama"
    iterations: int = 0
    max_iterations: int = MAX_ITERATIONS
    classification: Optional[dict] = None
    validated: bool = False
    cached: bool = False
    error: Optional[str] = None

def build_system_prompt() -> str:
    dominios_str = " | ".join(AGENT_DOMAINS)
    return f"""Eres un clasificador de tickets de soporte para un área de Shared Services.
Tu única tarea es analizar el texto del ticket y clasificarlo.

Reglas estrictas:
- Responde ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown.
- El campo "dominio" DEBE ser exactamente uno de: {dominios_str}
- El campo "prioridad" DEBE ser exactamente uno de: alta | media | baja
- El campo "categoria" describe el tipo específico dentro del dominio (libre)
- El campo "confianza" es un número entre 0.0 y 1.0

Ejemplo de respuesta correcta:
{{"dominio": "IT", "categoria": "incidente", "prioridad": "alta", "confianza": 0.95}}

Responde SOLO con el JSON, nada más."""

async def classify_node(state: AgentState) -> AgentState:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{LANGCHAIN_API_URL}/ask",
                json={
                    "prompt": state.texto,
                    "system": build_system_prompt(),
                    "provider": state.provider,
                }
            )
            response.raise_for_status()

        data = response.json()
        raw = data.get("response", "")

        # Capturar campo cached de langchain-api
        state.cached = data.get("cached", False)

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        state.classification = json.loads(raw)

    except json.JSONDecodeError:
        state.classification = None
        state.error = f"JSON inválido del LLM: {raw[:300]}"
    except Exception as e:
        state.classification = None
        state.error = f"Error en classify_node: {str(e)}"

    state.iterations += 1
    return state

async def validate_node(state: AgentState) -> AgentState:
    if not state.classification:
        state.validated = False
        return state

    try:
        ClasificacionSchema(**state.classification)
        state.validated = True
        state.error = None
    except Exception as e:
        state.validated = False
        state.error = str(e)

    return state

async def save_node(state: AgentState) -> AgentState:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        prioridad = state.classification["prioridad"]
        categoria = state.classification["categoria"]

        alerta = (
            f"URGENTE: ticket de {categoria} con prioridad alta"
            if prioridad == "alta"
            else f"Ticket de {categoria} registrado con prioridad {prioridad}"
        )

        ticket_id = await conn.fetchval(
            """INSERT INTO ss_tickets
               (texto, dominio, categoria, prioridad, confianza, origen, remitente, alerta)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            state.texto,
            state.classification["dominio"],
            state.classification["categoria"],
            state.classification["prioridad"],
            float(state.classification["confianza"]),
            state.origen,
            state.remitente,
            alerta,
        )

        state.classification["ticket_id"] = ticket_id
        state.classification["alerta"] = alerta

    finally:
        await conn.close()

    return state

def should_retry(state: AgentState) -> str:
    if state.validated:
        return "save"
    if state.iterations >= state.max_iterations:
        return END
    return "classify"

workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_node)
workflow.add_node("validate", validate_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("classify")
workflow.add_edge("classify", "validate")
workflow.add_conditional_edges(
    "validate",
    should_retry,
    {
        "save": "save",
        "classify": "classify",
        END: END,
    }
)
workflow.add_edge("save", END)

agent = workflow.compile()
