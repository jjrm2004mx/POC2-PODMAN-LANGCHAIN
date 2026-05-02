# Estándares del proyecto — ticket-classification

Este archivo es leído automáticamente por Claude Code en cada sesión.
Aplica estas reglas siempre que trabajes en este repositorio.

---

## Contexto del proyecto

`ticket-classification` clasifica tickets de soporte automáticamente usando LangGraph
y modelos LLM (Ollama local o proveedores cloud). Recibe tickets de `ticket-management`
vía API interna y persiste los resultados en su propia BD `classifier_db`.

Repositorio hermano principal: `ticket-management`
Red compartida: `shared-network` (externa, creada por `ticket-management`)

---

## Stack tecnológico

| Tecnología | Rol |
|---|---|
| Python 3.11 + FastAPI | Gateway API (`langchain-api`, puerto 8000) |
| LangGraph + LangChain | Agente de clasificación (`langchain-agent`, puerto 8001) |
| SQLAlchemy async + asyncpg | ORM — reemplazó asyncpg directo (Semana 3) |
| PostgreSQL 15 | BD `classifier_db` en puerto 5432 (interno) |
| Flyway CLI via Docker | Migraciones de BD |
| Redis | Cache LLM (MD5, TTL 1h) + estado del agente |
| Ollama | Modelos LLM locales |

---

## Convención de ramas

| Tipo | Prefijo |
|---|---|
| Funcionalidad nueva | `feature/` |
| Corrección de errores | `bugfix/` |
| Mantenimiento | `chore/` |
| Documentación | `docs/` |

Palabras separadas con guiones medios. Sin fechas ni nombres de personas.

---

## Convención de commits

Usar **Conventional Commits**:

```
<tipo>(<alcance>): <descripción en español en imperativo>
```

Alcances comunes: `agent`, `api`, `db`, `models`, `config`

---

## Reglas de código

- SQLAlchemy async (`AsyncSession`) para todas las operaciones de BD — no usar asyncpg directo
- El dedup de tickets se hace por `SELECT` previo, no por excepción `UniqueViolation`
- Variables de entorno en `.env` — nunca hardcodear credenciales

## Reglas de base de datos — Flyway CLI

- **Nunca ejecutar `ALTER TABLE` manualmente en la BD** — todo cambio de esquema va en una migración nueva (`V{N}__descripcion.sql`) en `db/migrations/postgresql/`
- Nunca modificar una migración ya aplicada — crear una nueva
- Flyway corre via Docker CLI (no JVM): `docker run --rm flyway/flyway migrate`
- Nomenclatura: inglés, plural snake_case, sin prefijos, máx 30 chars
- PK: `id` / FK: `{tabla_singular}_id` / timestamps: `created_at`, `updated_at`
- Booleanos: `is_{condicion}` (`is_validated`, `is_relevant`)

---

## Archivos clave

| Archivo | Propósito |
|---|---|
| `db/engine.py` | `create_async_engine` — conexión a `classifier_db` |
| `db/models.py` | Entidades SQLAlchemy: `Ticket`, `AgentRun`, `Attachment` |
| `db/queries.py` | 5 funciones async sobre `AsyncSession` |
| `langchain-agent/agent.py` | Lógica de clasificación LangGraph |
| `langchain-api/main.py` | Gateway FastAPI — endpoint `/process` |
| `db/migrations/postgresql/` | Migraciones Flyway |
