-- =============================================================================
-- shared-services-classifier — Schema inicial
-- Ejecutar desde WSL:
--   podman exec -i postgres psql -U admin -d ai < docs/init.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS ss_tickets (
    id                  SERIAL PRIMARY KEY,
    texto               TEXT NOT NULL,
    dominio             VARCHAR(50),
    categoria           VARCHAR(255),
    categoria_propuesta VARCHAR(255),
    requiere_revision   BOOLEAN DEFAULT FALSE,
    prioridad           VARCHAR(10),
    confianza           FLOAT,
    origen              VARCHAR(50),
    remitente           VARCHAR(255),
    alerta              TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ss_agent_runs (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(36) UNIQUE,
    ticket_id       INT REFERENCES ss_tickets(id),
    iterations_used INT,
    validated       BOOLEAN,
    provider_usado  VARCHAR(50),
    resultado       JSONB,
    duracion_ms     INT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Migración para despliegues existentes (idempotente)
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS categoria_propuesta  VARCHAR(255);
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS requiere_revision    BOOLEAN DEFAULT FALSE;
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS asunto               VARCHAR(500);
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS external_ticket_id   VARCHAR(36);
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS conversation_id      VARCHAR(200);

CREATE INDEX IF NOT EXISTS idx_tickets_conversation
ON ss_tickets(conversation_id)
WHERE conversation_id IS NOT NULL;

-- Tabla de metadatos de adjuntos (el contenido se almacenará en MinIO a futuro)
CREATE TABLE IF NOT EXISTS ss_adjuntos (
    id          SERIAL PRIMARY KEY,
    ticket_id   INT REFERENCES ss_tickets(id) ON DELETE CASCADE,
    nombre      VARCHAR(255) NOT NULL,
    tipo_mime   VARCHAR(100),
    storage_key VARCHAR(500),          -- Path en MinIO (uso futuro)
    created_at  TIMESTAMP DEFAULT NOW()
);
