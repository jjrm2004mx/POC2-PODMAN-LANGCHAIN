from langgraph.graph import StateGraph, END

from agent.state import AgentState, MIN_CONFIDENCE
from agent.nodes import classify_node, validate_node, save_node

# =============================================================================
# Grafo LangGraph: classify → validate → save (con retry)
# =============================================================================

def should_retry(state: AgentState) -> str:
    """
    Lógica de reintentos:
    - Iteraciones agotadas                                    → save (FALLBACK)
    - Sin clasificación válida                                → classify
    - Categoría no reconocida + confianza suficiente          → save (warning, categoryResolved=false es OK)
    - Categoría no reconocida + confianza baja                → classify con feedback
    - Confianza menor a MIN_CONFIDENCE                        → classify con feedback
    - Todo OK                                                 → save
    """
    from agent.catalog import _get_categorias

    if state.iterations >= state.max_iterations:
        print(f"[FALLBACK] Máximo de iteraciones alcanzado ({state.iterations}), enviando a save", flush=True)
        return "save"

    if not state.validated or not state.classification:
        return "classify"

    dominio           = state.classification.get("dominio", "")
    categoria         = state.classification.get("categoria", "")
    confianza         = float(state.classification.get("confianza", 0.0))
    requiere_revision = state.classification.get("requiere_revision", False)

    # Categoría fuera de catálogo con confianza suficiente → no reintentar,
    # el ticket se crea con categoryResolved=false (comportamiento esperado).
    if requiere_revision and confianza >= MIN_CONFIDENCE:
        cats     = _get_categorias(dominio)
        cats_str = ", ".join(cats) if cats else "ninguna configurada"
        print(
            f"[WARN] categoría '{categoria}' no reconocida para dominio '{dominio}' "
            f"(confianza={confianza:.2f}). Categorías válidas: {cats_str}. "
            f"Se enviará a save con requiere_revision=True.",
            flush=True,
        )
        return "save"

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
        state.validated      = False
        state.classification = None
        print(f"[RETRY {state.iterations}/{state.max_iterations}] {state.retry_feedback}", flush=True)
        return "classify"

    return "save"


workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_node)
workflow.add_node("validate", validate_node)
workflow.add_node("save",     save_node)

workflow.set_entry_point("classify")
workflow.add_edge("classify", "validate")
workflow.add_conditional_edges(
    "validate",
    should_retry,
    {
        "save":     "save",
        "classify": "classify",
        END:        END,
    },
)
workflow.add_edge("save", END)

agent = workflow.compile()
