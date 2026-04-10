-- =============================================================================
-- Migración: agregar email_id, thread_id y fecha_correo para soporte Gmail
-- Ejecutar desde WSL:
--   podman exec -i postgres psql -U admin -d ai < docs/migration_add_email_ids.sql
-- =============================================================================

-- ss_tickets: campos de identidad Gmail
ALTER TABLE ss_tickets
    ADD COLUMN IF NOT EXISTS email_id     TEXT,
    ADD COLUMN IF NOT EXISTS thread_id    TEXT,
    ADD COLUMN IF NOT EXISTS fecha_correo TIMESTAMPTZ;

-- Índice único en email_id — garantiza que un mismo mensaje no se procese dos veces
CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_email_id
    ON ss_tickets(email_id)
    WHERE email_id IS NOT NULL;

-- Índice en thread_id — usado para detectar replies al mismo hilo
CREATE INDEX IF NOT EXISTS idx_tickets_thread_id
    ON ss_tickets(thread_id)
    WHERE thread_id IS NOT NULL;

-- ss_enrichments: trazabilidad del mensaje que disparó el enriquecimiento
ALTER TABLE ss_enrichments
    ADD COLUMN IF NOT EXISTS email_id  TEXT,
    ADD COLUMN IF NOT EXISTS thread_id TEXT;

-- ss_tickets: tipo de clasificación del correo
ALTER TABLE ss_tickets
    ADD COLUMN IF NOT EXISTS email_type TEXT;  -- nuevo | reply | duplicado
