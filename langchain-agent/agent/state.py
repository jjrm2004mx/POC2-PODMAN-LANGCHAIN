import os
from difflib import SequenceMatcher
from pydantic import BaseModel, validator, root_validator
from typing import Optional, List

# =============================================================================
# Constantes de configuración
# =============================================================================

AGENT_DOMAINS   = os.getenv("AGENT_DOMAINS", "IT,cliente,operaciones,otro").split(",")
MAX_ITERATIONS  = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
FUZZY_THRESHOLD = int(os.getenv("FUZZY_THRESHOLD", "80"))
MIN_CONFIDENCE  = float(os.getenv("MIN_CONFIDENCE", "0.7"))

DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'admin')}"
    f":{os.getenv('POSTGRES_PASSWORD', 'admin')}"
    f"@{os.getenv('POSTGRES_HOST', 'postgres')}"
    f":{os.getenv('POSTGRES_PORT', '5432')}"
    f"/{os.getenv('POSTGRES_DB', 'ai')}"
)

LANGCHAIN_API_URL   = os.getenv("LANGCHAIN_API_URL", "http://langchain-api:8000")
AGENT_MOCK_CLASSIFY = os.getenv("AGENT_MOCK_CLASSIFY", "false").lower() == "true"
TICKET_MGMT_API_URL = os.getenv("TICKET_MGMT_API_URL")
TICKET_MGMT_API_KEY = os.getenv("TICKET_MGMT_API_KEY", "change-this-secret-key-in-production")
LLM_TIMEOUT         = float(os.getenv("LLM_TIMEOUT", "420"))

# =============================================================================
# ClasificacionSchema — validación Pydantic de la salida del LLM
# =============================================================================

def fuzzy_match_categoria(categoria: str, dominio: str) -> tuple:
    """Returns (categoria_final, categoria_propuesta, requiere_revision)"""
    from agent.catalog import _get_categorias
    cats = _get_categorias(dominio)
    if not cats:
        return categoria, None, False

    cat_lower = categoria.lower().strip()

    for c in cats:
        if c == cat_lower:
            return c, None, False

    best, best_score = max(
        ((c, SequenceMatcher(None, cat_lower, c).ratio() * 100) for c in cats),
        key=lambda x: x[1],
    )

    if best_score >= FUZZY_THRESHOLD:
        return best, categoria, False

    return categoria, categoria, True


class ClasificacionSchema(BaseModel):
    dominio:             str
    categoria:           str
    prioridad:           str
    confianza:           float
    categoria_propuesta: Optional[str] = None
    requiere_revision:   bool = False

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

    @root_validator(skip_on_failure=True)
    def aplicar_fuzzy(cls, values):
        dominio  = values.get("dominio")
        categoria = values.get("categoria")
        if dominio and categoria:
            final, propuesta, revision = fuzzy_match_categoria(categoria, dominio)
            values["categoria"]           = final
            values["categoria_propuesta"] = propuesta
            values["requiere_revision"]   = revision
        return values


# =============================================================================
# AgentState — estado compartido entre nodos del grafo LangGraph
# =============================================================================

class AgentState(BaseModel):
    asunto:            str
    cuerpo:            str
    origen:            str = "webhook"
    remitente:         Optional[str] = None
    nombre_remitente:  Optional[str] = None
    conversation_id:   Optional[str] = None  # SMTP Message-ID — solo auditoría
    email_id:          Optional[str] = None  # Gmail message ID — deduplicación
    thread_id:         Optional[str] = None  # Gmail thread ID — detección de reply
    fecha_correo:      Optional[str] = None  # Fecha ISO del correo
    email_type:        Optional[str] = None  # nuevo | reply | duplicado
    provider:          str = "ollama"
    iterations:        int = 0
    max_iterations:    int = MAX_ITERATIONS
    classification:    Optional[dict] = None
    adjuntos:          Optional[List[dict]] = []
    validated:         bool = False
    cached:            bool = False
    error:             Optional[str] = None
    retry_feedback:    Optional[str] = None

    class Config:
        # Permite que LangGraph actualice el estado entre nodos
        arbitrary_types_allowed = True
