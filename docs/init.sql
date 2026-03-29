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
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS categoria_propuesta VARCHAR(255);
ALTER TABLE ss_tickets ADD COLUMN IF NOT EXISTS requiere_revision   BOOLEAN DEFAULT FALSE;
