import os
import json
import httpx
from typing import Optional, List

from agent.state import (
    AgentState, ClasificacionSchema,
    LANGCHAIN_API_URL, AGENT_MOCK_CLASSIFY, MIN_CONFIDENCE,
)
from agent.catalog import _cargar_catalogo_remoto, _catalogo
from agent.prompts import build_system_prompt, SYSTEM_ENRICH
from db.queries import (
    insert_ticket, update_ticket_external_id,
    insert_enrichment,
)
from clients.ticket_mgmt import create_ticket, add_comment, add_attachments

# =============================================================================
# Nodos del grafo LangGraph
# =============================================================================

async def classify_node(state: AgentState) -> AgentState:
    if not _catalogo and os.getenv("TICKET_MGMT_CATALOGO_ENABLED", "true").lower() == "true":
        if _cargar_catalogo_remoto():
            print("[CATALOGO] Recargado exitosamente en classify_node", flush=True)
        else:
            print("[CATALOGO] Sigue sin disponible en classify_node — usando .env fallback", flush=True)

    if AGENT_MOCK_CLASSIFY:
        print("[MOCK] classify_node — saltando LLM, usando clasificación fija", flush=True)
        state.classification = {
            "dominio":   os.getenv("MOCK_DOMINIO",   "IT"),
            "categoria": os.getenv("MOCK_CATEGORIA", "acceso"),
            "prioridad": os.getenv("MOCK_PRIORIDAD", "BAJA"),
            "confianza": float(os.getenv("MOCK_CONFIANZA", "1.0")),
        }
        state.iterations += 1
        return state

    try:
        prompt = f"ASUNTO: {state.asunto}\n\nCUERPO: {state.cuerpo}"
        if state.retry_feedback:
            prompt += (
                f"\n\n⚠️ INTENTO ANTERIOR RECHAZADO: {state.retry_feedback}\n"
                "Debes corregir y responder SOLO con JSON válido usando las categorías listadas."
            )

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{LANGCHAIN_API_URL}/ask",
                json={
                    "prompt":   prompt,
                    "system":   build_system_prompt(),
                    "provider": state.provider,
                },
            )
            response.raise_for_status()

        data = response.json()
        raw  = data.get("response", "").strip()
        state.cached = data.get("cached", False)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()

        idx_start = raw.find("{")
        idx_end   = raw.rfind("}")
        if idx_start >= 0 and idx_end > idx_start:
            raw = raw[idx_start:idx_end + 1].strip()

        state.classification = json.loads(raw)

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
        state.classification["categoria"]           = validated.categoria
        state.classification["categoria_propuesta"] = validated.categoria_propuesta
        state.classification["requiere_revision"]   = validated.requiere_revision
        state.validated = True
        state.error     = None
    except Exception as e:
        state.validated = False
        state.error     = str(e)

    return state


async def save_node(state: AgentState) -> AgentState:
    if state.iterations >= state.max_iterations and (
        not state.classification
        or float(state.classification.get("confianza", 1.0)) < MIN_CONFIDENCE
    ):
        print(f"[FALLBACK] dominio='otro' aplicado en save_node tras {state.iterations} intentos", flush=True)
        state.classification = {
            "dominio":   "otro",
            "categoria": "general",
            "prioridad": "baja",
            "confianza": 0.0,
        }
        state.error = f"FALLBACK: sin clasificación válida tras {state.iterations} intentos"

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

    # Paso 1 — guardar en BD local
    ticket_id = await insert_ticket(
        cuerpo=state.cuerpo,
        asunto=state.asunto,
        dominio=dominio,
        categoria=categoria,
        prioridad=prioridad,
        confianza=float(confianza),
        origen=state.origen,
        remitente=state.remitente,
        nombre_remitente=state.nombre_remitente,
        alerta=alerta,
        categoria_propuesta=categoria_propuesta,
        requiere_revision=requiere_revision,
        conversation_id=state.conversation_id,
    )

    state.classification["ticket_id"]           = ticket_id
    state.classification["alerta"]              = alerta
    state.classification["categoria_propuesta"] = categoria_propuesta
    state.classification["requiere_revision"]   = requiere_revision

    # Paso 2 — crear ticket en ticket-management-backend
    try:
        external_ticket_id = await create_ticket(
            asunto=state.asunto,
            cuerpo=state.cuerpo,
            dominio=dominio,
            categoria=categoria,
            prioridad=prioridad,
            requiere_revision=requiere_revision,
            remitente=state.remitente or "",
            nombre_remitente=state.nombre_remitente or "",
            external_id=str(ticket_id),
            adjuntos=state.adjuntos or [],
        )
        await update_ticket_external_id(ticket_id, external_ticket_id)
        state.classification["external_ticket_id"] = external_ticket_id
    except Exception as e:
        print(f"[WARN TICKET-MGMT] No se pudo crear en ticket-management-backend: {type(e).__name__}: {repr(e)}", flush=True)
        state.classification["external_ticket_id"] = None

    return state


# =============================================================================
# Enriquecimiento de hilo — llamado desde main.py cuando DEDUP detecta
# una respuesta al hilo de un ticket ya existente.
# =============================================================================

async def enrich_ticket(
    *,
    external_ticket_id: str,
    ticket_id_local: int,
    ticket_asunto_original: str,
    ticket_dominio: str,
    ticket_categoria: str,
    asunto: str,
    cuerpo: str,
    remitente: Optional[str],
    nombre_remitente: Optional[str],
    adjuntos: List[dict],
    provider: str = "ollama",
) -> dict:
    """
    Retorna: {relevante, razon, comment_id, adjuntos_agregados}
    """
    if AGENT_MOCK_CLASSIFY:
        print("[MOCK] enrich_ticket — saltando LLM, usando enriquecimiento fijo", flush=True)
        llm_result = {
            "relevante": True,
            "razon":     "mock",
            "resumen":   f"{nombre_remitente or 'Remitente'} envió información adicional relevante (mock).",
        }
    else:
        adjuntos_str = (
            ", ".join(f"{a.get('nombre')} ({a.get('tipo', 'desconocido')})" for a in adjuntos)
            if adjuntos else "ninguno"
        )
        user_enrich = f"""TICKET EXISTENTE:
Asunto: {ticket_asunto_original}
Dominio: {ticket_dominio} / Categoría: {ticket_categoria}

RESPUESTA AL HILO:
Remitente: {nombre_remitente or "desconocido"} <{remitente or ""}>
Asunto: {asunto}
Adjuntos: {adjuntos_str}

Mensaje:
{cuerpo}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{LANGCHAIN_API_URL}/ask",
                    json={"prompt": user_enrich, "system": SYSTEM_ENRICH, "provider": provider},
                )
                response.raise_for_status()

            raw = response.json().get("response", "").strip()
            idx_start = raw.find("{")
            idx_end   = raw.rfind("}")
            if idx_start >= 0 and idx_end > idx_start:
                raw = raw[idx_start:idx_end + 1]
            llm_result = json.loads(raw)
            print(f"[ENRICH] LLM result: relevante={llm_result.get('relevante')} razon={llm_result.get('razon')}", flush=True)

        except Exception as e:
            print(f"[WARN enrich_ticket] Error en evaluación LLM: {e}", flush=True)
            return {"relevante": False, "razon": f"error LLM: {e}", "comment_id": None, "adjuntos_agregados": 0}

    if not llm_result.get("relevante"):
        return {"relevante": False, "razon": llm_result.get("razon"), "comment_id": None, "adjuntos_agregados": 0}

    nombre  = nombre_remitente or "Remitente"
    email   = remitente or ""
    resumen = llm_result.get("resumen") or f"{nombre} envió información adicional al hilo del ticket."
    texto_comentario = f"{nombre} <{email}> {resumen}" if email else f"{nombre} {resumen}"

    comment_id         = None
    adjuntos_agregados = 0

    try:
        comment_id = await add_comment(
            external_ticket_id=external_ticket_id,
            texto=texto_comentario,
        )
    except Exception as e:
        print(f"[WARN enrich_ticket] Error agregando comentario: {e}", flush=True)

    if adjuntos:
        try:
            adjuntos_agregados = await add_attachments(
                external_ticket_id=external_ticket_id,
                adjuntos=adjuntos,
            )
        except Exception as e:
            print(f"[WARN enrich_ticket] Error agregando adjuntos: {e}", flush=True)

    return {
        "relevante":          True,
        "razon":              llm_result.get("razon"),
        "comment_id":         comment_id,
        "adjuntos_agregados": adjuntos_agregados,
    }
