import os
import re
import json
import httpx
from typing import Optional, List

from agent.state import (
    AgentState, ClasificacionSchema,
    LANGCHAIN_API_URL, AGENT_MOCK_CLASSIFY, AGENT_PREPROCESS_EMAIL,
    MIN_CONFIDENCE, LLM_TIMEOUT, ENRICH_LLM_TIMEOUT,
)
from agent.catalog import _cargar_catalogo_remoto, _catalogo
from agent.prompts import build_system_prompt, SYSTEM_ENRICH
from db.queries import (
    insert_ticket, update_ticket_external_id,
    insert_enrichment,
)
from clients.ticket_mgmt import create_ticket, add_comment, add_attachments

# =============================================================================
# Pre-procesamiento del cuerpo del correo (activado con AGENT_PREPROCESS_EMAIL=true)
# Elimina ruido estructural del correo para reducir el contexto enviado al LLM.
# Útil para modelos locales con capacidad de instrucción-following limitada.
# Para modelos cloud (OpenAI, Anthropic) se recomienda desactivarlo.
# =============================================================================

# Patrones que marcan el inicio del hilo citado
_QUOTED_THREAD_RE = re.compile(
    r"(^|\n)(De:|From:|Enviado el:|Sent:|-----+\s*Mensaje original)",
    re.IGNORECASE,
)
# Imágenes embebidas en firma (logos, banners, fotos de perfil)
_EMBEDDED_IMAGE_RE = re.compile(
    r"\[image:[^\]]*\]|\[Imagen quitada[^\]]*\]",
    re.IGNORECASE,
)
# Links mailto y URLs entre < >
_MAILTO_RE = re.compile(r"<mailto:[^>]+>|<https?://[^>]+>", re.IGNORECASE)
# Avisos legales reconocibles por frases clave
_LEGAL_DISCLAIMER_RE = re.compile(
    r"(PROTECCIÓN DE DATOS PERSONALES|confidencial y restringida|"
    r"La información contenida en este mensaje es confidencial)",
    re.IGNORECASE,
)


def clean_email_body(cuerpo: str) -> str:
    """Elimina ruido estructural del cuerpo del correo antes de enviarlo al LLM."""
    # 1. Cortar en el inicio del hilo citado (conservar solo el mensaje principal)
    match = _QUOTED_THREAD_RE.search(cuerpo)
    if match:
        cuerpo = cuerpo[:match.start()].strip()

    # 2. Eliminar imágenes embebidas de firma
    cuerpo = _EMBEDDED_IMAGE_RE.sub("", cuerpo)

    # 3. Eliminar links mailto y URLs entre < >
    cuerpo = _MAILTO_RE.sub("", cuerpo)

    # 4. Cortar aviso legal si quedó en el mensaje principal
    match_legal = _LEGAL_DISCLAIMER_RE.search(cuerpo)
    if match_legal:
        cuerpo = cuerpo[:match_legal.start()].strip()

    return cuerpo.strip()


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
        cuerpo_llm = clean_email_body(state.cuerpo) if AGENT_PREPROCESS_EMAIL else state.cuerpo
        if AGENT_PREPROCESS_EMAIL:
            print(f"[PREPROCESS] cuerpo original: {len(state.cuerpo)} chars → limpio: {len(cuerpo_llm)} chars", flush=True)
        else:
            print(f"[CLASSIFY] cuerpo: {len(state.cuerpo)} chars", flush=True)
        adj_nombres = [a.get("nombre", "?") for a in (state.adjuntos or [])]
        if adj_nombres:
            print(f"[CLASSIFY] adjuntos recibidos ({len(adj_nombres)}): {adj_nombres}", flush=True)
        prompt = f"ASUNTO: {state.asunto}\n\nCUERPO: {cuerpo_llm}"
        print(f"[CLASSIFY] prompt total: {len(prompt)} chars → enviando a {state.provider}", flush=True)
        if state.retry_feedback:
            prompt += (
                f"\n\n⚠️ INTENTO ANTERIOR RECHAZADO: {state.retry_feedback}\n"
                "Debes corregir y responder SOLO con JSON válido usando las categorías listadas."
            )

        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
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
        state.classification["nombre_ticket"]       = validated.nombre_ticket
        state.classification["descripcion"]         = validated.descripcion
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
    nombre_ticket       = state.classification.get("nombre_ticket") or state.asunto
    descripcion         = state.classification.get("descripcion") or state.cuerpo

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
        email_id=state.email_id,
        thread_id=state.thread_id,
        fecha_correo=state.fecha_correo,
        email_type=state.email_type,
    )

    state.classification["ticket_id"]           = ticket_id
    state.classification["alerta"]              = alerta
    state.classification["categoria_propuesta"] = categoria_propuesta
    state.classification["requiere_revision"]   = requiere_revision
    state.classification["nombre_ticket"]       = nombre_ticket
    state.classification["descripcion"]         = descripcion

    # Paso 2 — crear ticket en ticket-management-backend
    try:
        external_ticket_id = await create_ticket(
            asunto=nombre_ticket,
            cuerpo=descripcion,
            dominio=dominio,
            categoria=categoria,
            prioridad=prioridad,
            requiere_revision=requiere_revision,
            remitente=state.remitente or "",
            nombre_remitente=state.nombre_remitente or "",
            external_id=str(ticket_id),
            adjuntos=[],  # Los adjuntos con b64 se suben desde main.py tras el grafo
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
            async with httpx.AsyncClient(timeout=ENRICH_LLM_TIMEOUT) as client:
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
            print(
                f"[ENRICH] LLM result: relevante={llm_result.get('relevante')} razon={llm_result.get('razon')}\n"
                f"[ENRICH] Contenido evaluado:\n{user_enrich}",
                flush=True,
            )

        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
            # Error transitorio de red — asumir relevante para no perder la actualización del ticket
            print(f"[WARN enrich_ticket] Timeout LLM ({repr(e)}), se asume relevante y se continúa.", flush=True)
            llm_result = {"relevante": True, "razon": f"timeout LLM: {repr(e)}", "resumen": None}

        except Exception as e:
            print(f"[WARN enrich_ticket] Error en evaluación LLM: {repr(e)}", flush=True)
            return {"relevante": False, "razon": f"error LLM: {repr(e)}", "comment_id": None, "adjuntos_agregados": 0}

    if not llm_result.get("relevante"):
        return {"relevante": False, "razon": llm_result.get("razon"), "comment_id": None, "adjuntos_agregados": 0}

    nombre  = nombre_remitente or "Remitente"
    email   = remitente or ""
    resumen = llm_result.get("resumen")
    if not resumen:
        # El LLM no generó resumen — usar el cuerpo del email truncado como respaldo
        cuerpo_corto = (cuerpo[:300] + "…") if len(cuerpo) > 300 else cuerpo
        resumen = f"Información adicional recibida: {cuerpo_corto}"
    texto_comentario = f"{nombre} <{email}> {resumen}" if email else f"{nombre} {resumen}"

    comment_id         = None
    adjuntos_agregados = 0

    try:
        comment_id = await add_comment(
            external_ticket_id=external_ticket_id,
            texto=texto_comentario,
        )
    except httpx.HTTPStatusError as e:
        print(
            f"[WARN enrich_ticket] Error agregando comentario: "
            f"HTTP {e.response.status_code} — {e.response.text}",
            flush=True,
        )
    except Exception as e:
        print(f"[WARN enrich_ticket] Error agregando comentario: {repr(e)}", flush=True)

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
