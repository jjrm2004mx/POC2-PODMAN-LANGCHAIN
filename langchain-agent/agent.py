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
        if not v or not isinstance(v, str):
            raise ValueError("dominio NO PUEDE estar vacío")
        v = v.strip()
        if v not in AGENT_DOMAINS:
            raise ValueError(f"dominio '{v}' no está en {AGENT_DOMAINS}")
        return v

    @validator("categoria")
    def categoria_valida(cls, v):
        if not v or len(str(v).strip()) < 3:
            raise ValueError(f"categoria DEBE tener al menos 3 caracteres, recibido: '{v}'")
        return v.strip()

    @validator("prioridad")
    def prioridad_valida(cls, v):
        if not v or v not in ["alta", "media", "baja"]:
            raise ValueError(f"prioridad '{v}' DEBE ser: alta | media | baja")
        return v

    @validator("confianza")
    def confianza_valida(cls, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"confianza NO es numérica: {v}")
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confianza {v} DEBE estar entre 0.0 y 1.0")
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
    return f"""CLASIFICADOR DE TICKETS SHARED SERVICES
================================================================
INSTRUCCIONES CRÍTICAS:
1. SOLO RESPONDE CON JSON VÁLIDO
2. SIN EXPLICACIONES, SIN MARKDOWN, SIN BACKTICKS
3. FILA 1: El JSON completo
4. NADA MÁS DESPUÉS

DOMINIOS VÁLIDOS (elige UNO):
- IT
- cliente
- operaciones
- otro

PRIORIDADES VÁLIDAS (elige UNA):
- alta
- media
- baja

CAMPOS REQUERIDOS:
{{"dominio": "IT", "categoria": "descripción corta", "prioridad": "alta", "confianza": 0.95}}

EJEMPLO CORRECTO:
{{"dominio": "operaciones", "categoria": "costos", "prioridad": "media", "confianza": 0.85}}

REGLAS:
✓ "dominio" DEBE ser: {dominios_str}
✓ "prioridad" DEBE ser: alta, media o baja
✓ "categoria" es texto libre, NUNCA vacío (mínimo 3 caracteres)
✓ "confianza" es NÚMERO entre 0.0 y 1.0

FORMATO FINAL OBLIGATORIO:
{{"dominio":"...", "categoria":"...", "prioridad":"...", "confianza":X.XX}}
================================================================"""

async def classify_node(state: AgentState) -> AgentState:
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minutos para llama3:latest
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
        raw = data.get("response", "").strip()

        # Capturar campo cached de langchain-api
        state.cached = data.get("cached", False)

        # ─ LIMPIEZA ROBUSTA DE MARKDOWN Y BASURA ───────────────────────
        # 1. Remover backticks con "json"
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()
        
        # 2. Buscar primer { válido y último }
        idx_start = raw.find("{")
        idx_end = raw.rfind("}")
        
        if idx_start >= 0 and idx_end > idx_start:
            raw = raw[idx_start:idx_end+1].strip()
        
        # 3. Intentar parse JSON
        state.classification = json.loads(raw)
        
        # 4. Validar que tenga al menos los 4 campos
        required = {"dominio", "categoria", "prioridad", "confianza"}
        if not required.issubset(state.classification.keys()):
            missing = required - set(state.classification.keys())
            raise ValueError(f"Campos faltantes: {missing}")

    except json.JSONDecodeError as e:
        state.classification = None
        state.error = f"JSON inválido del LLM (línea {e.lineno}): {raw[:200]}"
        print(f"[DEBUG classify_node] JSONDecodeError: {state.error}", flush=True)
        
    except ValueError as e:
        state.classification = None
        state.error = f"Validación JSON falló: {str(e)}"
        print(f"[DEBUG classify_node] ValueError: {state.error}", flush=True)
        
    except Exception as e:
        state.classification = None
        state.error = f"Error en classify_node: {str(e)}"
        print(f"[DEBUG classify_node] Exception: {state.error}", flush=True)

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
        dominio = state.classification["dominio"]
        categoria = state.classification["categoria"]
        prioridad = state.classification["prioridad"]
        confianza = state.classification["confianza"]

        # Detectar si es fallback (confianza 0.0 + dominio "otro")
        is_fallback = dominio == "otro" and confianza == 0.0
        
        if is_fallback:
            alerta = f"⚠️ FALLBACK: Sin clasificación válida tras {state.iterations} intentos. Revisar manualmente."
        elif prioridad == "alta":
            alerta = f"🚨 URGENTE: {categoria} con prioridad alta"
        else:
            alerta = f"📌 Ticket de {categoria} registrado con prioridad {prioridad}"

        ticket_id = await conn.fetchval(
            """INSERT INTO ss_tickets
               (texto, dominio, categoria, prioridad, confianza, origen, remitente, alerta)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            state.texto,
            dominio,
            categoria,
            prioridad,
            float(confianza),
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
    """
    Lógica de reintentos con FALLBACK:
    - Si clasificación válida → guardar
    - Si alcanzó MAX_ITERATIONS sin validación → FALLBACK a "otro"
    - Si aún hay intentos → reintentar classify
    """
    if state.validated:
        return "save"
    
    # 🚨 FALLBACK: Si se agotaron intentos, asignar "otro"
    if state.iterations >= state.max_iterations:
        state.classification = {
            "dominio": "otro",
            "categoria": "sin clasificar - máximo de reintentos",
            "prioridad": "baja",
            "confianza": 0.0,  # Confianza mínima indica fallback
        }
        state.validated = True
        state.error = f"FALLBACK activado después de {state.iterations} intentos"
        print(f"[FALLBACK] Asignado dominio='otro' tras {state.iterations} intentos fallidos", flush=True)
        return "save"
    
    # Reintentar clasificación
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
