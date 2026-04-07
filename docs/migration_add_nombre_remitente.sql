-- =============================================================================
-- Migración: agregar columna nombre_remitente a ss_tickets
-- Ejecutar desde WSL:
--   podman exec -i postgres psql -U admin -d ai < docs/migration_add_nombre_remitente.sql
-- =============================================================================

ALTER TABLE ss_tickets
    ADD COLUMN IF NOT EXISTS nombre_remitente VARCHAR(255);
