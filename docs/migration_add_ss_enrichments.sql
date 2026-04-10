-- =============================================================================
-- Migración: crear tabla ss_enrichments para auditoría de enriquecimientos
-- Ejecutar desde WSL:
--   podman exec -i postgres psql -U admin -d ai < docs/migration_add_ss_enrichments.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS ss_enrichments (
    id                  SERIAL PRIMARY KEY,
    ticket_id           INTEGER REFERENCES ss_tickets(id),
    conversation_id     TEXT,
    remitente           TEXT,
    nombre_remitente    TEXT,
    relevante           BOOLEAN NOT NULL,
    razon               TEXT,
    comment_id          TEXT,           -- UUID del comentario en ticket-management-backend
    adjuntos_agregados  INTEGER DEFAULT 0,
    creado_en           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enrichments_ticket_id
ON ss_enrichments(ticket_id);

CREATE INDEX IF NOT EXISTS idx_enrichments_conversation
ON ss_enrichments(conversation_id)
WHERE conversation_id IS NOT NULL;
