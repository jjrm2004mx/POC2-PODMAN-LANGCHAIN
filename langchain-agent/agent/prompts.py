from agent.state import AGENT_DOMAINS
from agent.catalog import _get_categorias

# =============================================================================
# Prompts del agente — clasificación y evaluación de enriquecimiento
# =============================================================================

def build_system_prompt() -> str:
    dominios_str = " | ".join(AGENT_DOMAINS)

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
{chr(10).join(f"- {d}" for d in AGENT_DOMAINS)}

PRIORIDADES VÁLIDAS (elige UNA):
- alta
- media
- baja
{cats_section}

CAMPOS REQUERIDOS:
{{"dominio": "{AGENT_DOMAINS[0]}", "categoria": "descripción corta", "prioridad": "alta", "confianza": 0.95}}

EJEMPLO CORRECTO:
{{"dominio": "{AGENT_DOMAINS[1] if len(AGENT_DOMAINS) > 1 else AGENT_DOMAINS[0]}", "categoria": "soporte", "prioridad": "media", "confianza": 0.85}}

REGLAS:
✓ "dominio" DEBE ser: {dominios_str}
✓ "prioridad" DEBE ser: alta, media o baja
✓ "categoria" DEBE ser una de las categorías válidas listadas arriba
✓ "confianza" es NÚMERO entre 0.0 y 1.0

FORMATO FINAL OBLIGATORIO:
{{"dominio":"...", "categoria":"...", "prioridad":"...", "confianza":X.XX}}
================================================================"""


SYSTEM_ENRICH = """Eres un evaluador de enriquecimiento de tickets de soporte.
Determina si un mensaje de respuesta al hilo aporta información relevante al ticket existente.

RESPONDE SOLO CON JSON VÁLIDO. SIN MARKDOWN. SIN BACKTICKS.
{"relevante": true/false, "razon": "justificación breve", "resumen": "resumen en tercera persona comenzando con el nombre del remitente (solo si relevante, si no: null)"}

RELEVANTE si contiene:
- Adjuntos nuevos (logs, capturas, documentos, reportes)
- Información adicional del problema (pasos, contexto, datos técnicos)
- Correcciones o aclaraciones a la descripción original
- Urgencia adicional o impacto no mencionado antes

NO RELEVANTE si es:
- Acuse de recibo ("gracias", "ok", "recibido", "entendido")
- Solo saludos o mensajes vacíos
- Confirmaciones sin información nueva"""
