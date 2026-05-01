-- =============================================================================
-- V1 — Schema inicial consolidado
-- BD: classifier_db (reemplaza a "ai")
-- Flyway corre este script desde cero — sin baseline previo.
-- Nomenclatura: inglés, plural snake_case, sin prefijos, máx 30 chars.
-- =============================================================================

CREATE TABLE tickets (
    id                  SERIAL          PRIMARY KEY,
    body                TEXT            NOT NULL,
    subject             VARCHAR(500),
    domain              VARCHAR(50),
    category            VARCHAR(255),
    suggested_category  VARCHAR(255),
    requires_review     BOOLEAN         DEFAULT FALSE,
    priority            VARCHAR(10),
    confidence          FLOAT,
    source              VARCHAR(50)     DEFAULT 'webhook',
    sender              VARCHAR(255),
    sender_name         VARCHAR(255),
    alert               TEXT,
    external_ticket_id  VARCHAR(36),
    conversation_id     VARCHAR(200),
    email_id            TEXT,
    thread_id           TEXT,
    email_received_at   TIMESTAMPTZ,
    email_type          TEXT,
    created_at          TIMESTAMP       DEFAULT NOW()
);

CREATE INDEX idx_tickets_conversation_id
    ON tickets (conversation_id)
    WHERE conversation_id IS NOT NULL;

-- -----------------------------------------------------------------------------

CREATE TABLE agent_runs (
    id              SERIAL      PRIMARY KEY,
    run_id          UUID        DEFAULT gen_random_uuid() UNIQUE,
    ticket_id       INT         REFERENCES tickets (id),
    iterations_used INT,
    is_validated    BOOLEAN,
    provider        VARCHAR(50),
    result          JSONB,
    duration_ms     INT,
    created_at      TIMESTAMP   DEFAULT NOW()
);

-- -----------------------------------------------------------------------------

CREATE TABLE attachments (
    id           SERIAL        PRIMARY KEY,
    ticket_id    INT           REFERENCES tickets (id) ON DELETE CASCADE,
    filename     VARCHAR(255)  NOT NULL,
    content_type VARCHAR(100),
    storage_key  VARCHAR(500),
    created_at   TIMESTAMP     DEFAULT NOW()
);

-- -----------------------------------------------------------------------------

CREATE TABLE enrichments (
    id                SERIAL      PRIMARY KEY,
    ticket_id         INT         REFERENCES tickets (id),
    conversation_id   TEXT,
    sender            TEXT,
    sender_name       TEXT,
    is_relevant       BOOLEAN     NOT NULL,
    reason            TEXT,
    comment_id        TEXT,
    attachments_count INTEGER     DEFAULT 0,
    email_id          TEXT,
    thread_id         TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_enrichments_ticket_id
    ON enrichments (ticket_id);

CREATE INDEX idx_enrichments_conversation_id
    ON enrichments (conversation_id)
    WHERE conversation_id IS NOT NULL;
