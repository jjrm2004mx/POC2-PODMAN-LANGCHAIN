# =============================================================================
# langchain-agent/agent.py
# Grafo LangGraph: classify → validate → save
# =============================================================================

import os
import json
import httpx
import asyncpg
from difflib import SequenceMatcher
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, validator, root_validator
from typing import Optional

AGENT_DOMAINS = os.getenv("AGENT_DOMAINS", "IT,cliente,operaciones,otro").split(",")
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
FUZZY_THRESHOLD = int(os.getenv("FUZZY_THRESHOLD", "80"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.7"))

# =============================================================================
# CATÁLOGO REMOTO — cargado desde SS-TICKET-SYSTEM al arrancar
# Si el servicio no está disponible, se usa el fallback del .env
# _catalogo[dominio] = [categoria1, categoria2, ...]
# =============================================================================
_catalogo: dict = {}

def _cargar_catalogo_remoto() -> bool:
    """
    Consulta GET /internal/classifications/active en SS-TICKET-SYSTEM.
    Carga el catálogo en _catalogo si responde correctamente.
    Timeout corto (3s) — nunca bloquea el arranque.
    Retorna True si cargó correctamente, False si usó fallback.
    """
    global _catalogo, AGENT_DOMAINS
    url = f"{os.getenv('SS_TICKET_API_URL', 'http://ss-ticket-backend:8080/api/v1')}/internal/classifications/active"
    api_key = os.getenv("SS_TICKET_API_KEY", "change-this-secret-key-in-production")
    try:
        import httpx as _httpx
        resp = _httpx.get(url, headers={"X-Api-Key": api_key}, timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
        catalogo_nuevo = {}
        for item in data:
            nombre = item.get("name", "").strip()
            cats   = [c["name"].strip().lower() for c in item.get("categories", []) if c.get("name")]
            if nombre:
                catalogo_nuevo[nombre] = cats
        if catalogo_nuevo:
            _catalogo = catalogo_nuevo
            AGENT_DOMAINS = list(_catalogo.keys())
            print(f"[CATALOGO] Cargado desde SS-TICKET-SYSTEM: {list(_catalogo.keys())}", flush=True)
            return True
    except Exception as e:
        print(f"[CATALOGO] No disponible, usando .env como fallback: {e}", flush=True)
    return False

def _get_categorias(dominio: str) -> list:
    # Primero busca en el catálogo remoto, luego en .env
    if _catalogo:
        return _catalogo.get(dominio, [])
    raw = os.getenv(f"CATEGORIES_{dominio.upper()}", "")
    return [c.strip().lower() for c in raw.split(",") if c.strip()] if raw else []

# Intentar cargar catálogo al importar el módulo (arranque del agente)
if os.getenv("SS_TICKET_CATALOGO_ENABLED", "true").lower() == "true":
    _cargar_catalogo_remoto()
else:
    print("[CATALOGO] Deshabilitado — usando .env como fuente de catálogo", flush=True)

def fuzzy_match_categoria(categoria: str, dominio: str) -> tuple:
    """Returns (categoria_final, categoria_propuesta, requiere_revision)"""
    cats = _get_categorias(dominio)
    if not cats:
        return categoria, None, False  # Sin lista configurada → aceptar tal cual

    cat_lower = categoria.lower().strip()

    # Match exacto (case-insensitive)
    for c in cats:
        if c == cat_lower:
            return c, None, False

    # Fuzzy match — mejor puntuación
    best, best_score = max(
        ((c, SequenceMatcher(None, cat_lower, c).ratio() * 100) for c in cats),
        key=lambda x: x[1],
    )

    if best_score >= FUZZY_THRESHOLD:
        return best, categoria, False  # Corregida; guardar original como propuesta

    # Categoría desconocida → marcar para revisión
    return categoria, categoria, True
LANGCHAIN_API_URL = os.getenv("LANGCHAIN_API_URL", "http://langchain-api:8000")
SS_TICKET_API_URL = os.getenv("SS_TICKET_API_URL", "http://ss-ticket-backend:8080/api/v1")
SS_TICKET_API_KEY = os.getenv("SS_TICKET_API_KEY", "change-this-secret-key-in-production")
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
    categoria_propuesta: Optional[str] = None
    requiere_revision: bool = False

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
        dominio = values.get("dominio")
        categoria = values.get("categoria")
        if dominio and categoria:
            final, propuesta, revision = fuzzy_match_categoria(categoria, dominio)
            values["categoria"] = final
            values["categoria_propuesta"] = propuesta
            values["requiere_revision"] = revision
        return values

class AgentState(BaseModel):
    asunto: str
    cuerpo: str
    origen: str = "webhook"
    remitente: Optional[str] = None
    conversation_id: Optional[str] = None
    provider: str = "ollama"
    iterations: int = 0
    max_iterations: int = MAX_ITERATIONS
    classification: Optional[dict] = None
    validated: bool = False
    cached: bool = False
    error: Optional[str] = None
    retry_feedback: Optional[str] = None  # Retroalimentación al LLM en reintentos

def build_system_prompt() -> str:
    dominios_str = " | ".join(AGENT_DOMAINS)

    # Construir sección de categorías válidas por dominio
    cats_lines = []
    for dominio in AGENT_DOMAINS:
        cats = _get_categorias(dominio)
        if cats:
            cats_lines.append(f"  {dominio}: {', '.join(cats)}")
    cats_section = (
        "\nCATEGORÍAS VÁLIDAS POR DOMINIO (usa EXACTAMENTE una de estas):\n" + "\n".join(cats_lines)
        if cats_lines else
        "\n(Sin lista de categorías configurada — usa texto libre descriptivo)"
    )

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
{cats_section}

CAMPOS REQUERIDOS:
{{"dominio": "IT", "categoria": "descripción corta", "prioridad": "alta", "confianza": 0.95}}

EJEMPLO CORRECTO:
{{"dominio": "operaciones", "categoria": "logistica", "prioridad": "media", "confianza": 0.85}}

REGLAS:
✓ "dominio" DEBE ser: {dominios_str}
✓ "prioridad" DEBE ser: alta, media o baja
✓ "categoria" DEBE ser una de las categorías válidas listadas arriba
✓ "confianza" es NÚMERO entre 0.0 y 1.0

FORMATO FINAL OBLIGATORIO:
{{"dominio":"...", "categoria":"...", "prioridad":"...", "confianza":X.XX}}
================================================================"""

async def classify_node(state: AgentState) -> AgentState:
    try:
        prompt = f"ASUNTO: {state.asunto}\n\nCUERPO: {state.cuerpo}"
        if state.retry_feedback:
            prompt += f"\n\n⚠️ INTENTO ANTERIOR RECHAZADO: {state.retry_feedback}\nDebes corregir y responder SOLO con JSON válido usando las categorías listadas."
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minutos para llama3:latest
            response = await client.post(
                f"{LANGCHAIN_API_URL}/ask",
                json={
                    "prompt": prompt,
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
        import traceback
        state.classification = None
        state.error = f"Error en classify_node: {str(e)}"
        print(f"[DEBUG classify_node] Exception: {state.error}\n{traceback.format_exc()}", flush=True)

    state.iterations += 1
    return state

async def validate_node(state: AgentState) -> AgentState:
    if not state.classification:
        state.validated = False
        return state

    try:
        validated = ClasificacionSchema(**state.classification)
        # Escribir de vuelta los campos corregidos por fuzzy matching
        state.classification["categoria"]           = validated.categoria
        state.classification["categoria_propuesta"] = validated.categoria_propuesta
        state.classification["requiere_revision"]   = validated.requiere_revision
        state.validated = True
        state.error = None
    except Exception as e:
        state.validated = False
        state.error = str(e)

    return state

async def save_node(state: AgentState) -> AgentState:
    dominio             = state.classification["dominio"]
    categoria           = state.classification["categoria"]
    prioridad           = state.classification["prioridad"]
    confianza           = state.classification["confianza"]
    categoria_propuesta = state.classification.get("categoria_propuesta")
    requiere_revision   = state.classification.get("requiere_revision", False)

    is_fallback = dominio == "otro" and confianza == 0.0

    if is_fallback:
        alerta = f"⚠️ FALLBACK: Sin clasificación válida tras {state.iterations} intentos. Revisar manualmente."
    elif requiere_revision:
        alerta = f"🔍 REVISIÓN: categoría '{categoria}' no reconocida, requiere validación manual"
    elif prioridad == "alta":
        alerta = f"🚨 URGENTE: {categoria} con prioridad alta"
    else:
        alerta = f"📌 Ticket de {categoria} registrado con prioridad {prioridad}"

    # ─── PASO 1: guardar en nuestra BD ────────────────────────────────────────
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        ticket_id = await conn.fetchval(
            """INSERT INTO ss_tickets
               (texto, asunto, dominio, categoria, prioridad, confianza, origen, remitente, alerta,
                categoria_propuesta, requiere_revision, conversation_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
               RETURNING id""",
            state.cuerpo,
            state.asunto,
            dominio,
            categoria,
            prioridad,
            float(confianza),
            state.origen,
            state.remitente,
            alerta,
            categoria_propuesta,
            requiere_revision,
            state.conversation_id,
        )
    finally:
        await conn.close()

    state.classification["ticket_id"]           = ticket_id
    state.classification["alerta"]              = alerta
    state.classification["categoria_propuesta"] = categoria_propuesta
    state.classification["requiere_revision"]   = requiere_revision

    # ─── PASO 2: crear ticket en SS-TICKET-SYSTEM ─────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SS_TICKET_API_URL}/internal/tickets",
                headers={"X-Api-Key": SS_TICKET_API_KEY},
                params={
                    "title":               state.asunto,
                    "description":         state.cuerpo,
                    "asunto":              state.asunto,
                    "cuerpo":              state.cuerpo,
                    "classificationName":  dominio,
                    "categoryName":        categoria,
                    "priority":            prioridad.upper(),
                    "requiereValidacion":  requiere_revision,
                    "requesterEmail":      state.remitente or "",
                    "externalId":          str(ticket_id),
                },
            )
            resp.raise_for_status()
            ss_data = resp.json()
            external_ticket_id = ss_data.get("ticketId")
            print(
                f"[SS-TICKET] ticketId={external_ticket_id} "
                f"result={ss_data.get('result')} "
                f"classificationResolved={ss_data.get('classificationResolved')} "
                f"categoryResolved={ss_data.get('categoryResolved')}",
                flush=True,
            )

        # ─── PASO 3: actualizar nuestra BD con el ID externo ──────────────────
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute(
                "UPDATE ss_tickets SET external_ticket_id = $1 WHERE id = $2",
                external_ticket_id,
                ticket_id,
            )
        finally:
            await conn.close()

        state.classification["external_ticket_id"] = external_ticket_id

    except Exception as e:
        # El ticket ya está en nuestra BD — el error externo no es bloqueante
        print(f"[WARN SS-TICKET] No se pudo crear en SS-TICKET-SYSTEM: {e}", flush=True)
        state.classification["external_ticket_id"] = None

    return state

def should_retry(state: AgentState) -> str:
    """
    Lógica de reintentos:
    - Categoría no reconocida (requiere_revision=True) → reintentar con feedback
    - Confianza menor a MIN_CONFIDENCE                 → reintentar con feedback
    - Ambas condiciones OK                             → guardar
    - Agotó MAX_ITERATIONS                             → FALLBACK dominio=otro
    """
    # ─── FALLBACK: iteraciones agotadas ──────────────────────────────────────
    if state.iterations >= state.max_iterations:
        state.classification = {
            "dominio": "otro",
            "categoria": "sin clasificar - máximo de reintentos",
            "prioridad": "baja",
            "confianza": 0.0,
        }
        state.validated = True
        state.error = f"FALLBACK activado después de {state.iterations} intentos"
        print(f"[FALLBACK] dominio='otro' tras {state.iterations} intentos", flush=True)
        return "save"

    # ─── Sin clasificación válida → reintentar ────────────────────────────────
    if not state.validated or not state.classification:
        return "classify"

    dominio   = state.classification.get("dominio", "")
    categoria = state.classification.get("categoria", "")
    confianza = float(state.classification.get("confianza", 0.0))
    requiere_revision = state.classification.get("requiere_revision", False)

    motivos = []

    if requiere_revision:
        cats     = _get_categorias(dominio)
        cats_str = ", ".join(cats) if cats else "ninguna configurada"
        motivos.append(
            f"categoría '{categoria}' no reconocida para dominio '{dominio}'. "
            f"Categorías válidas: {cats_str}"
        )

    if confianza < MIN_CONFIDENCE:
        motivos.append(
            f"confianza {confianza:.2f} es menor al mínimo requerido {MIN_CONFIDENCE:.2f}. "
            f"Analiza mejor el ticket y asigna una categoría más precisa"
        )

    if motivos:
        state.retry_feedback = " | ".join(motivos)
        state.validated = False
        state.classification = None
        print(f"[RETRY {state.iterations}/{state.max_iterations}] {state.retry_feedback}", flush=True)
        return "classify"

    return "save"

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
