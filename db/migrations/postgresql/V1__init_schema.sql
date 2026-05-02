-- ========================================
-- V1__init_schema.sql (VERSIÓN 0 CONSOLIDADA)
-- ========================================
-- Esquema completo del Ticket Classification Service
-- Consolidación de V1-V2 (baseline ambiente fresco)
-- Columnas eliminadas post-auditoría: email_id, thread_id, email_type
-- email_received_at se conserva (feature pendiente: propagar desde n8n)
-- storage_key en attachments se conserva (análisis futuro: OCR/NLP sobre PDFs)
-- enrichments eliminada: sin uso ni plan concreto

CREATE TABLE tickets (
    id                 SERIAL        PRIMARY KEY,
    body               TEXT          NOT NULL,
    subject            VARCHAR(500),
    domain             VARCHAR(50),
    category           VARCHAR(255),
    suggested_category VARCHAR(255),
    requires_review    BOOLEAN       DEFAULT FALSE,
    priority           VARCHAR(10),
    confidence         FLOAT,
    source             VARCHAR(50),
    sender             VARCHAR(255),
    sender_name        VARCHAR(255),
    alert              TEXT,
    external_ticket_id VARCHAR(36),
    conversation_id    VARCHAR(200),
    email_received_at  TIMESTAMP,
    created_at         TIMESTAMP     DEFAULT NOW()
);

CREATE INDEX idx_tickets_conversation_id
    ON tickets(conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE TABLE agent_runs (
    id              SERIAL      PRIMARY KEY,
    run_id          VARCHAR(36) UNIQUE,
    ticket_id       INT         REFERENCES tickets(id),
    iterations_used INT,
    is_validated    BOOLEAN,
    provider        VARCHAR(50),
    result          JSONB,
    duration_ms     INT,
    created_at      TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX idx_agent_runs_ticket_id
    ON agent_runs(ticket_id);

CREATE TABLE attachments (
    id           SERIAL        PRIMARY KEY,
    ticket_id    INT           REFERENCES tickets(id) ON DELETE CASCADE,
    filename     VARCHAR(255)  NOT NULL,
    content_type VARCHAR(100),
    storage_key  VARCHAR(500),
    created_at   TIMESTAMP     DEFAULT NOW()
);

CREATE INDEX idx_attachments_ticket_id
    ON attachments(ticket_id);
