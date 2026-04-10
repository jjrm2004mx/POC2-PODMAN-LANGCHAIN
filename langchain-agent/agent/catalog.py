import os
from agent.state import AGENT_DOMAINS, TICKET_MGMT_API_URL, TICKET_MGMT_API_KEY

# =============================================================================
# Catálogo remoto de dominios y categorías
# Cargado desde ticket-management-backend al arrancar.
# Si no está disponible, se usa el fallback del .env
# _catalogo[dominio] = [categoria1, categoria2, ...]
# =============================================================================

_catalogo: dict = {}


def _cargar_catalogo_remoto() -> bool:
    """
    Consulta GET /internal/classifications/active en ticket-management-backend.
    Timeout corto (3s) — nunca bloquea el arranque.
    Retorna True si cargó correctamente, False si usó fallback.
    """
    global _catalogo
    import agent.state as _state

    url     = f"{TICKET_MGMT_API_URL}/internal/classifications/active"
    api_key = TICKET_MGMT_API_KEY
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
            _state.AGENT_DOMAINS = list(_catalogo.keys())
            print(f"[CATALOGO] Cargado desde ticket-management-backend: {list(_catalogo.keys())}", flush=True)
            return True
    except Exception as e:
        print(f"[CATALOGO] No disponible, usando .env como fallback: {e}", flush=True)
    return False


def _get_categorias(dominio: str) -> list:
    if _catalogo:
        return _catalogo.get(dominio, [])
    raw = os.getenv(f"CATEGORIES_{dominio.upper()}", "")
    return [c.strip().lower() for c in raw.split(",") if c.strip()] if raw else []


# Cargar al importar el módulo
if os.getenv("TICKET_MGMT_CATALOGO_ENABLED", "true").lower() == "true":
    _cargar_catalogo_remoto()
else:
    print("[CATALOGO] Deshabilitado — usando .env como fuente de catálogo", flush=True)
