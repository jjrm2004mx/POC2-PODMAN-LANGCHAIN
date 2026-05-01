# CLAUDE.md — ticket-classification

## Stack

- Python 3.11 / FastAPI / LangGraph
- PostgreSQL 15 (`classifier_db`, puerto 5432) — migrado desde `ai`
- asyncpg (conexión directa — SQLAlchemy async en Semana 3)
- Redis 7 (cache de LLM y estado de jobs)
- Flyway CLI via Docker (gestión de migraciones)
- Podman / podman-compose (runtime local en WSL2)

## Convención de nomenclatura de BD (inglés universal)

**Regla:** Todos los identificadores de BD en inglés, plural snake_case, sin prefijos, máx 30 caracteres.

| Elemento | Convención | Ejemplo |
|---|---|---|
| Tablas | plural snake_case sin prefijo | `tickets`, `agent_runs` |
| PK | `id` | `id SERIAL PRIMARY KEY` |
| FK | `{singular}_id` | `ticket_id` |
| Timestamps | `created_at`, `updated_at` | `created_at TIMESTAMP DEFAULT NOW()` |
| Booleanos | `is_{condicion}` | `is_validated`, `is_relevant` |
| Índices | `idx_{tabla}_{columna}` | `idx_tickets_conversation_id` |
| Únicos | `uq_{tabla}_{columna}` | `uq_agent_runs_run_id` |

**Tablas actuales:** `tickets`, `agent_runs`, `attachments`, `enrichments`

> Nunca usar prefijos (`ss_`, `tbl_`), nombres en español, ni `ALTER TABLE` manual.
> Todos los cambios de schema van en una nueva migración Flyway.

## Migraciones

- Ubicación: `db/migrations/postgresql/`
- Naming: `V{N}__{descripcion_snake_case}.sql` (doble guión bajo)
- Seeds repeatables: `R__{descripcion}.sql`
- Flyway se ejecuta con Flyway CLI via Docker (ver instrucciones en WSL)

## Variables de entorno

Ver `env.txt` para la plantilla completa. El `.env` real va en WSL (no se commitea).

Variables de BD:
```
POSTGRES_USER=admin
POSTGRES_PASSWORD=...
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=classifier_db
```

## Ramas y commits

- Git Flow: `feature/`, `bugfix/`, `hotfix/`, `chore/`, `docs/` desde `develop`
- Conventional Commits en español imperativo: `feat(agent): agregar nodo de enriquecimiento`
