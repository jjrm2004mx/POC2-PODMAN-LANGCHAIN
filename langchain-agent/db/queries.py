import asyncpg
from typing import Optional
from agent.state import DATABASE_URL

# =============================================================================
# Queries asyncpg — todas las operaciones de base de datos en un solo lugar
# =============================================================================

async def get_ticket_by_conversation_id(conversation_id: str) -> Optional[asyncpg.Record]:
    """Retorna id, external_ticket_id, asunto, dominio, categoria del ticket o None."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetchrow(
            "SELECT id, external_ticket_id, asunto, dominio, categoria "
            "FROM ss_tickets WHERE conversation_id = $1",
            conversation_id,
        )
    finally:
        await conn.close()


async def insert_ticket(
    *,
    cuerpo: str,
    asunto: str,
    dominio: str,
    categoria: str,
    prioridad: str,
    confianza: float,
    origen: str,
    remitente: Optional[str],
    nombre_remitente: Optional[str],
    alerta: str,
    categoria_propuesta: Optional[str],
    requiere_revision: bool,
    conversation_id: Optional[str],
) -> int:
    """Inserta un ticket en ss_tickets y retorna el id generado."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetchval(
            """INSERT INTO ss_tickets
               (texto, asunto, dominio, categoria, prioridad, confianza, origen, remitente,
                nombre_remitente, alerta, categoria_propuesta, requiere_revision, conversation_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               RETURNING id""",
            cuerpo, asunto, dominio, categoria, prioridad, float(confianza),
            origen, remitente, nombre_remitente, alerta,
            categoria_propuesta, requiere_revision, conversation_id,
        )
    finally:
        await conn.close()


async def update_ticket_external_id(ticket_id: int, external_ticket_id: str) -> None:
    """Actualiza el external_ticket_id (UUID de ticket-management-backend) en ss_tickets."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE ss_tickets SET external_ticket_id = $1 WHERE id = $2",
            external_ticket_id, ticket_id,
        )
    finally:
        await conn.close()


async def insert_agent_run(
    *,
    run_id: str,
    ticket_id: Optional[int],
    iterations_used: int,
    validated: bool,
    provider_usado: str,
    resultado: Optional[str],
    duracion_ms: int,
) -> None:
    """Registra una ejecución del agente en ss_agent_runs."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """INSERT INTO ss_agent_runs
               (run_id, ticket_id, iterations_used, validated,
                provider_usado, resultado, duracion_ms)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)""",
            run_id, ticket_id, iterations_used, validated,
            provider_usado, resultado, duracion_ms,
        )
    finally:
        await conn.close()


async def insert_adjunto(ticket_id: int, nombre: str, tipo_mime: Optional[str]) -> None:
    """Inserta metadatos de un adjunto en ss_adjuntos."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO ss_adjuntos (ticket_id, nombre, tipo_mime) VALUES ($1, $2, $3)",
            ticket_id, nombre, tipo_mime,
        )
    finally:
        await conn.close()


async def insert_enrichment(
    *,
    ticket_id: int,
    conversation_id: Optional[str],
    remitente: Optional[str],
    nombre_remitente: Optional[str],
    relevante: bool,
    razon: Optional[str],
    comment_id: Optional[str],
    adjuntos_agregados: int,
) -> None:
    """Registra el resultado de una evaluación de enriquecimiento en ss_enrichments."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """INSERT INTO ss_enrichments
               (ticket_id, conversation_id, remitente, nombre_remitente,
                relevante, razon, comment_id, adjuntos_agregados)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            ticket_id, conversation_id, remitente, nombre_remitente,
            relevante, razon, comment_id, adjuntos_agregados,
        )
    finally:
        await conn.close()
