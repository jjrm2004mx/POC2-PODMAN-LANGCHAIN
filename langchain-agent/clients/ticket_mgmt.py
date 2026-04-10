import sys
import base64
import httpx
from typing import Optional, List
from agent.state import TICKET_MGMT_API_URL, TICKET_MGMT_API_KEY

# =============================================================================
# Cliente HTTP para ticket-management-backend
# Centraliza todas las llamadas a la API externa en un solo lugar.
# =============================================================================

def _headers() -> dict:
    return {"X-Api-Key": TICKET_MGMT_API_KEY}


async def create_ticket(
    *,
    asunto: str,
    cuerpo: str,
    dominio: str,
    categoria: str,
    prioridad: str,
    requiere_revision: bool,
    remitente: str,
    nombre_remitente: str,
    external_id: str,
    adjuntos: List[dict],
) -> Optional[str]:
    """
    Crea un ticket en ticket-management-backend.
    Retorna el ticketId (UUID) o None si falla.
    """
    data = {
        "title":              asunto,
        "description":        cuerpo,
        "asunto":             asunto,
        "cuerpo":             cuerpo,
        "classificationName": dominio,
        "categoryName":       categoria,
        "priority":           prioridad.upper(),
        "requiereValidacion": "true" if requiere_revision else "false",
        "requesterEmail":     remitente or "",
        "requesterName":      nombre_remitente or "",
        "externalId":         str(external_id),
    }

    files_ss = []
    for adj in adjuntos:
        nombre   = adj.get("nombre", "adjunto")
        tipo     = adj.get("tipo") or "application/octet-stream"
        b64      = adj.get("contenido_b64") or ""
        try:
            contenido = base64.b64decode(b64) if b64 else b""
        except Exception:
            contenido = b""
        if not contenido:
            contenido = f"[ARCHIVO DE PRUEBA] {nombre}".encode()
        files_ss.append(("anexos", (nombre, contenido, tipo)))

    multipart = [(k, (None, str(v), "text/plain")) for k, v in data.items()]
    multipart += files_ss

    print(
        f"[TICKET-MGMT REQUEST] URL={TICKET_MGMT_API_URL}/internal/tickets "
        f"data={data} adjuntos={len(files_ss)}",
        flush=True, file=sys.stdout,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TICKET_MGMT_API_URL}/internal/tickets",
            headers=_headers(),
            files=multipart,
        )
        print(f"[TICKET-MGMT RESPONSE] status={resp.status_code} body={resp.text}", flush=True, file=sys.stdout)
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
        return external_ticket_id


async def add_comment(
    *,
    external_ticket_id: str,
    texto: str,
    autor: str = "langchain-agent",
    origen: str = "enrichment",
) -> Optional[str]:
    """
    Agrega un comentario a un ticket existente.
    Retorna el commentId (UUID) o None si falla.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TICKET_MGMT_API_URL}/internal/tickets/{external_ticket_id}/comments",
            headers=_headers(),
            json={"texto": texto, "autor": autor, "origen": origen},
        )
        resp.raise_for_status()
        comment_id = resp.json().get("commentId")
        print(f"[ENRICH] Comentario agregado commentId={comment_id}", flush=True, file=sys.stdout)
        return comment_id


async def add_attachments(
    *,
    external_ticket_id: str,
    adjuntos: List[dict],
) -> int:
    """
    Adjunta archivos a un ticket existente.
    Retorna la cantidad de adjuntos agregados correctamente.
    """
    files_ss = []
    for adj in adjuntos:
        nombre   = adj.get("nombre", "adjunto")
        tipo     = adj.get("tipo") or "application/octet-stream"
        b64      = adj.get("contenido_b64") or ""
        try:
            contenido = base64.b64decode(b64) if b64 else b""
        except Exception:
            contenido = b""
        if not contenido:
            contenido = f"[ARCHIVO DE PRUEBA] {nombre}".encode()
        files_ss.append(("anexos", (nombre, contenido, tipo)))

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TICKET_MGMT_API_URL}/internal/tickets/{external_ticket_id}/attachments",
            headers=_headers(),
            files=files_ss,
        )
        resp.raise_for_status()
        count = len(resp.json().get("adjuntosAgregados", []))
        print(f"[ENRICH] {count} adjunto(s) agregado(s)", flush=True, file=sys.stdout)
        return count
