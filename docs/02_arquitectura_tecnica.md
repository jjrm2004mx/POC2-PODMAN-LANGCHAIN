# 02 — Arquitectura Técnica — Referencia Completa
## shared-services-classifier · LangChain Agent + Podman
**Evolución: Automation → Autonomous Systems · Marzo 2026**

---

## Índice

1. [Visión general del stack](#1-visión-general-del-stack)
2. [docker-compose.yml — anatomía completa](#2-docker-composeyml--anatomía-completa)
3. [LangChain Agent — núcleo de orquestación](#3-langchain-agent--núcleo-de-orquestación)
4. [FastAPI Gateway — patrones y dependencias](#4-fastapi-gateway--patrones-y-dependencias)
5. [Modelo de datos](#5-modelo-de-datos)
6. [Observabilidad — Prometheus, Grafana, Loki](#6-observabilidad--prometheus-grafana-loki)
7. [Red interna Podman](#7-red-interna-podman)
8. [Variables de entorno — referencia completa](#8-variables-de-entorno--referencia-completa)
9. [Dependencias Python](#9-dependencias-python)
10. [Workflow del agente — arquitectura detallada](#10-workflow-del-agente--arquitectura-detallada)
11. [Migración desde n8n — equivalencias](#11-migración-desde-n8n--equivalencias)
12. [Roadmap de evolución](#12-roadmap-de-evolución)

---

## 1. Visión general del stack

### Contexto de evolución

| Fase anterior (POC2 — n8n) | Esta arquitectura |
|---|---|
| n8n como orquestador visual | LangChain Agent programático |
| Docker Compose | Podman Compose (rootless, sin daemon) |
| Flujos estáticos nodo a nodo | Loops dinámicos con decisión autónoma |
| Lógica fija en nodos JSON | Lógica flexible en código Python |
| Sin validación de salidas del LLM | Validación Pydantic + retry automático |
| Categorías hardcodeadas | Dominios configurables vía variable de entorno |
| Un solo origen (webhook o gmail) | Multi-origen con campo `origen` explícito |

### Diagrama de arquitectura completa

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              HOST MACHINE                               │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       PODMAN NETWORK                              │  │
│  │                                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐ │  │
│  │  │  CAPA DE ENTRADA                                            │ │  │
│  │  │  langchain-agent :8001  ←── POST /process                  │ │  │
│  │  │  (Webhook HTTP / Gmail / Slack / Manual)                   │ │  │
│  │  └──────────────────────────────┬──────────────────────────────┘ │  │
│  │                                 │                                 │  │
│  │  ┌──────────────────────────────▼──────────────────────────────┐ │  │
│  │  │  CAPA DE AGENTE — LangGraph                                 │ │  │
│  │  │                                                             │ │  │
│  │  │  ┌───────────┐   ┌───────────┐   ┌─────────────────────┐   │ │  │
│  │  │  │ classify  │──▶│ validate  │──▶│ save                │   │ │  │
│  │  │  └───────────┘   └─────┬─────┘   └─────────────────────┘   │ │  │
│  │  │        ▲               │ ❌ retry (máx AGENT_MAX_ITERATIONS) │ │  │
│  │  │        └───────────────┘                                    │ │  │
│  │  └─────────────────────────────────────────────────────────────┘ │  │
│  │                                 │                                 │  │
│  │  ┌──────────────────────────────▼──────────────────────────────┐ │  │
│  │  │  CAPA DE IA — langchain-api :8000                           │ │  │
│  │  │  Patrón Adapter + Strategy                                  │ │  │
│  │  │  ┌──────────┬──────────┬───────────┬─────────────┐         │ │  │
│  │  │  │  Ollama  │  OpenAI  │ Anthropic │   Gemini    │         │ │  │
│  │  │  │  local   │  cloud   │  cloud    │   cloud     │         │ │  │
│  │  │  └────┬─────┴──────────┴───────────┴─────────────┘         │ │  │
│  │  └───────┼─────────────────────────────────────────────────────┘ │  │
│  │          │                                                        │  │
│  │  ┌───────▼──────────────┐                                        │  │
│  │  │  ollama :11434       │  llama3.2:3b (local, sin internet)     │  │
│  │  └──────────────────────┘                                        │  │
│  │                                                                   │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │  CAPA DE DATOS                                           │    │  │
│  │  │  postgres :5432    DB: ai | ss_tickets, ss_agent_runs    │    │  │
│  │  │  redis    :6379    Cache LLM (MD5, TTL 1h) + estado      │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  │                                                                   │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │  CAPA DE OBSERVABILIDAD                                  │    │  │
│  │  │  prometheus :9090 │ grafana :3000 │ loki :3100           │    │  │
│  │  │  promtail         │ node-exporter :9100                  │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

Cloud externo:
  LangSmith  ← trazas automáticas del agente
  OpenAI API ← si provider=openai
  Anthropic  ← si provider=anthropic
  Gemini     ← si provider=gemini
```

### Resumen de puertos y acceso

| Servicio | URL | Credenciales |
|---|---|---|
| LangChain Agent | http://localhost:8001 | sin auth |
| Agent Swagger | http://localhost:8001/docs | sin auth |
| LangChain API | http://localhost:8000 | sin auth |
| API Swagger | http://localhost:8000/docs | sin auth |
| Ollama | http://localhost:11434 | sin auth |
| PostgreSQL | localhost:5432 | admin / admin / db:ai |
| Redis | localhost:6379 | sin auth |
| Prometheus | http://localhost:9090 | sin auth |
| Grafana | http://localhost:3000 | admin / admin |
| Node Exporter | http://localhost:9100 | sin auth |
| Loki | http://localhost:3100 | sin auth |

---

## 2. docker-compose.yml — anatomía completa

> El archivo se llama `docker-compose.yml` por convención (podman-compose
> lo lee automáticamente). El runtime es Podman — no Docker.

### Servicio: `langchain-agent` (nuevo — reemplaza n8n)

```yaml
langchain-agent:
  build: ./langchain-agent
  container_name: langchain-agent
  ports:
    - "8001:8001"
  environment:
    - AGENT_HOST=0.0.0.0
    - AGENT_PORT=8001
    - LANGCHAIN_API_URL=http://langchain-api:8000
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_DB=ai
    - POSTGRES_USER=admin
    - POSTGRES_PASSWORD=admin
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2}
    - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY}
    - LANGCHAIN_PROJECT=${LANGCHAIN_PROJECT}
    - AGENT_MAX_ITERATIONS=5
    - AGENT_PROVIDER=ollama
    - AGENT_DOMAINS=${AGENT_DOMAINS}
    - VALIDATION_ENABLED=true
  volumes:
    - ./langchain-agent:/app    # Hot reload en desarrollo
  depends_on:
    - langchain-api
    - postgres
    - redis
  restart: always
```

### Servicio: `langchain-api` (gateway de IA — sin cambios respecto a POC2)

```yaml
langchain-api:
  build: ./langchain-api
  container_name: langchain-api
  ports:
    - "8000:8000"
  environment:
    - MODEL_PROVIDER=ollama
    - OLLAMA_BASE_URL=http://ollama:11434
    - OLLAMA_MODEL=${OLLAMA_MODEL}
    - OPENAI_API_KEY=${OPENAI_API_KEY}
    - OPENAI_MODEL=${OPENAI_MODEL}
    - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    - ANTHROPIC_MODEL=${ANTHROPIC_MODEL}
    - GEMINI_API_KEY=${GEMINI_API_KEY}
    - GEMINI_MODEL=${GEMINI_MODEL}
    - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2}
    - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY}
    - LANGCHAIN_PROJECT=${LANGCHAIN_PROJECT}
    - REDIS_HOST=redis
    - REDIS_PORT=6379
  depends_on:
    - ollama
    - postgres
    - redis
  restart: always
```

### Servicios de infraestructura

```yaml
postgres:
  image: postgres:15
  container_name: postgres
  ports: ["5432:5432"]
  environment:
    POSTGRES_USER: admin
    POSTGRES_PASSWORD: admin
    POSTGRES_DB: ai
  volumes:
    - ./postgres_data:/var/lib/postgresql/data
  restart: always

ollama:
  image: ollama/ollama
  container_name: ollama
  ports: ["11434:11434"]
  volumes:
    - ./ollama_data:/root/.ollama
  restart: always

redis:
  image: redis:7-alpine
  container_name: redis
  ports: ["6379:6379"]
  restart: always
```

### Servicios de observabilidad

```yaml
prometheus:
  image: prom/prometheus:latest
  container_name: prometheus
  ports: ["9090:9090"]
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  restart: always

grafana:
  image: grafana/grafana:latest
  container_name: grafana
  ports: ["3000:3000"]
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
  volumes:
    - ./grafana_data:/var/lib/grafana
  depends_on: [prometheus, loki]
  restart: always

node-exporter:
  image: prom/node-exporter:latest
  container_name: node-exporter
  ports: ["9100:9100"]
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
    - /:/rootfs:ro
  command:
    - --path.procfs=/host/proc
    - --path.sysfs=/host/sys
    - --collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)
  restart: always

loki:
  image: grafana/loki:2.9.0
  container_name: loki
  ports: ["3100:3100"]
  command: -config.file=/etc/loki/local-config.yaml
  restart: always

promtail:
  image: grafana/promtail:latest
  container_name: promtail
  volumes:
    - /var/log/pods:/var/log/pods:ro            # Ruta para Podman rootless
    - ./promtail.yml:/etc/promtail/config.yml
  command: -config.file=/etc/promtail/config.yml
  depends_on: [loki]
  restart: always
```

> **Nota:** El `docker-compose.yml` original usaba n8n y n8n-worker.
> En esta arquitectura esos dos servicios se eliminan — son reemplazados
> por `langchain-agent`.

---

## 3. LangChain Agent — núcleo de orquestación

### Arquitectura del agente (LangGraph)

```
POST /process
     │
     ▼
┌─────────────┐
│ Input Parser │  ← Pydantic: valida que el request sea correcto
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                  LangGraph — StateGraph               │
│                                                      │
│  ┌───────────┐   ┌───────────┐   ┌───────────────┐  │
│  │ classify  │──▶│ validate  │──▶│     save      │  │
│  │           │   │           │   │               │  │
│  │ Llama a   │   │ Pydantic  │   │ INSERT INTO   │  │
│  │ LangChain │   │ schema    │   │ ss_tickets    │  │
│  │ API /ask  │   │ check     │   │ ss_agent_runs │  │
│  └───────────┘   └─────┬─────┘   └───────────────┘  │
│       ▲                │ ❌                           │
│       └────────────────┘                             │
│         retry (máx AGENT_MAX_ITERATIONS)             │
└──────────────────────────────────────────────────────┘
       │
       ▼
Response 200: {dominio, categoria, categoria_propuesta, requiere_revision, prioridad, confianza, ...}
```

### Código base del agente (`langchain-agent/agent.py`)

```python
# langchain-agent/agent.py
import os
import json
import httpx
import asyncpg
from difflib import SequenceMatcher
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, validator, root_validator
from typing import Optional

# ── Dominios y categorías configurables desde variables de entorno ─
AGENT_DOMAINS  = os.getenv("AGENT_DOMAINS", "IT,cliente,operaciones,otro").split(",")
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
FUZZY_THRESHOLD = int(os.getenv("FUZZY_THRESHOLD", "80"))
LANGCHAIN_API_URL = os.getenv("LANGCHAIN_API_URL", "http://langchain-api:8000")
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

def fuzzy_match_categoria(categoria: str, dominio: str) -> tuple:
    """Devuelve (categoria_final, categoria_propuesta, requiere_revision).
    - Match exacto  → acepta tal cual.
    - Match fuzzy ≥ FUZZY_THRESHOLD → corrige y guarda original como propuesta.
    - Sin match     → marca requiere_revision=True para revisión manual.
    """
    cats = [c.strip().lower()
            for c in os.getenv(f"CATEGORIES_{dominio.upper()}", "").split(",") if c.strip()]
    if not cats:
        return categoria, None, False
    cat_lower = categoria.lower().strip()
    for c in cats:
        if c == cat_lower:
            return c, None, False
    best, score = max(((c, SequenceMatcher(None, cat_lower, c).ratio() * 100) for c in cats),
                      key=lambda x: x[1])
    if score >= FUZZY_THRESHOLD:
        return best, categoria, False
    return categoria, categoria, True

# ── Schema de clasificación (validación Pydantic + fuzzy matching) ─
class ClasificacionSchema(BaseModel):
    dominio: str
    categoria: str
    prioridad: str
    confianza: float
    categoria_propuesta: Optional[str] = None  # sugerencia original del LLM si fue corregida
    requiere_revision: bool = False             # True si la categoría no está en la lista

    @validator("dominio")
    def dominio_valido(cls, v):
        if v not in AGENT_DOMAINS:
            raise ValueError(f"dominio '{v}' no está en {AGENT_DOMAINS}")
        return v

    @validator("prioridad")
    def prioridad_valida(cls, v):
        if v not in ["alta", "media", "baja"]:
            raise ValueError(f"prioridad '{v}' debe ser: alta, media o baja")
        return v

    @validator("confianza")
    def confianza_valida(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confianza {v} debe estar entre 0.0 y 1.0")
        return v

    @root_validator
    def aplicar_fuzzy(cls, values):
        dominio  = values.get("dominio")
        categoria = values.get("categoria")
        if dominio and categoria:
            final, propuesta, revision = fuzzy_match_categoria(categoria, dominio)
            values["categoria"]           = final
            values["categoria_propuesta"] = propuesta
            values["requiere_revision"]   = revision
        return values

# ── Estado del agente ─────────────────────────────────────────────
class AgentState(BaseModel):
    texto: str
    origen: str = "webhook"
    remitente: Optional[str] = None
    provider: str = "ollama"
    iterations: int = 0
    max_iterations: int = MAX_ITERATIONS
    classification: Optional[dict] = None
    validated: bool = False
    error: Optional[str] = None

# ── System prompt del clasificador ────────────────────────────────
def build_system_prompt() -> str:
    dominios_str = " | ".join(AGENT_DOMAINS)
    return f"""Eres un clasificador de tickets de soporte para un área de Shared Services.
Tu única tarea es analizar el texto del ticket y clasificarlo.

Reglas estrictas:
- Responde ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown.
- El campo "dominio" DEBE ser exactamente uno de: {dominios_str}
- El campo "prioridad" DEBE ser exactamente uno de: alta | media | baja
- El campo "categoria" se valida contra la lista `CATEGORIES_{DOMINIO}` del .env con fuzzy matching (umbral `FUZZY_THRESHOLD`)
- El campo "confianza" es un número entre 0.0 y 1.0

Ejemplo de respuesta correcta:
{{"dominio": "IT", "categoria": "incidente", "prioridad": "alta", "confianza": 0.95}}

Responde SOLO con el JSON, nada más."""

# ── Nodos del grafo ───────────────────────────────────────────────
async def classify_node(state: AgentState) -> AgentState:
    """Llama a langchain-api para clasificar el texto."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{LANGCHAIN_API_URL}/ask",
            json={
                "prompt": state.texto,
                "system": build_system_prompt(),
                "provider": state.provider,
            }
        )
        response.raise_for_status()

    raw = response.json()["response"]
    try:
        state.classification = json.loads(raw)
    except json.JSONDecodeError:
        state.classification = None
        state.error = f"JSON inválido del LLM: {raw[:200]}"

    state.iterations += 1
    return state

async def validate_node(state: AgentState) -> AgentState:
    """Valida la clasificación contra el schema Pydantic."""
    if not state.classification:
        state.validated = False
        state.error = "classification es None — el LLM no devolvió JSON válido"
        return state

    try:
        ClasificacionSchema(**state.classification)
        state.validated = True
        state.error = None
    except Exception as e:
        state.validated = False
        state.error = str(e)

    return state

async def save_node(state: AgentState) -> AgentState:
    """Persiste el resultado en PostgreSQL."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Generar alerta según prioridad
        prioridad = state.classification["prioridad"]
        categoria = state.classification["categoria"]
        alerta = (
            f"URGENTE: ticket de {categoria} con prioridad alta"
            if prioridad == "alta"
            else f"Ticket de {categoria} registrado con prioridad {prioridad}"
        )

        # Insertar ticket
        ticket_id = await conn.fetchval(
            """INSERT INTO ss_tickets
               (texto, dominio, categoria, prioridad, confianza, origen, remitente, alerta)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            state.texto,
            state.classification["dominio"],
            state.classification["categoria"],
            state.classification["prioridad"],
            state.classification["confianza"],
            state.origen,
            state.remitente,
            alerta,
        )

        state.classification["ticket_id"] = ticket_id
        state.classification["alerta"] = alerta
    finally:
        await conn.close()

    return state

# ── Router de decisión ────────────────────────────────────────────
def should_retry(state: AgentState) -> str:
    if state.validated:
        return "save"
    if state.iterations >= state.max_iterations:
        return END  # Máximo de intentos alcanzado
    return "classify"  # Reintentar con instrucciones

# ── Compilar el grafo ─────────────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_node)
workflow.add_node("validate", validate_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("classify")
workflow.add_edge("classify", "validate")
workflow.add_conditional_edges(
    "validate",
    should_retry,
    {"save": "save", "classify": "classify", END: END}
)
workflow.add_edge("save", END)

agent = workflow.compile()
```

### Request / Response del endpoint `/process`

```json
// Request — POST http://localhost:8001/process
{
  "texto": "El servidor de producción no responde desde las 9am",
  "origen": "webhook",        // webhook | gmail | slack | email | manual
  "remitente": null,          // Email del remitente (solo para origen=gmail)
  "provider": "ollama",       // Opcional — default: AGENT_PROVIDER del .env
  "max_iterations": 5         // Opcional — default: AGENT_MAX_ITERATIONS del .env
}

// Response exitosa — categoría reconocida (match exacto o fuzzy)
{
  "run_id": "uuid-...",
  "dominio": "IT",
  "categoria": "servidor",               // categoria canónica (corregida si hubo fuzzy)
  "categoria_propuesta": "servidorr",    // sugerencia original del LLM (null si match exacto)
  "requiere_revision": false,            // true si la categoría no está en la lista configurada
  "prioridad": "alta",
  "confianza": 0.95,
  "alerta": "🚨 URGENTE: servidor con prioridad alta",
  "texto_original": "El servidor de producción no responde desde las 9am",
  "origen": "webhook",
  "remitente": null,
  "iterations_used": 1,
  "cached": false,
  "validated": true
}

// Response con categoría nueva (no está en CATEGORIES_IT)
{
  "run_id": "uuid-...",
  "dominio": "IT",
  "categoria": "kubernetes",             // se guarda tal cual
  "categoria_propuesta": "kubernetes",   // igual al original para trazar
  "requiere_revision": true,             // admin debe revisar y añadir a la lista
  "prioridad": "media",
  "confianza": 0.80,
  "alerta": "🔍 REVISIÓN: categoría 'kubernetes' no reconocida, requiere validación manual",
  "texto_original": "...",
  "origen": "webhook",
  "iterations_used": 1,
  "cached": false,
  "validated": true
}

// Response con error (máximo de iteraciones alcanzado)
{
  "run_id": "uuid-...",
  "error": "Máximo de iteraciones alcanzado sin clasificación válida",
  "iterations_used": 5,
  "validated": false,
  "last_error": "dominio 'support' no está en ['IT', 'cliente', 'operaciones', 'otro']"
}
```

---

## 4. FastAPI Gateway — patrones y dependencias

### Patrón Adapter + Strategy

```
                    ┌─────────────────────┐
                    │      FastAPI         │
                    │   POST /ask          │
                    │   {provider: "ollama"}│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Strategy Router    │
                    │ get_strategy(provider)│
                    └──────────┬──────────┘
                               │
            ┌──────────┬───────┴────────┬──────────┐
            ▼          ▼                ▼           ▼
    ┌──────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
    │OllamaAdapter │ │OpenAI   │ │Anthropic │ │GeminiAdapter │
    │llama3.2:3b   │ │gpt-4o-  │ │claude-3-5│ │gemini-1.5-   │
    │local         │ │mini     │ │-haiku    │ │flash         │
    └──────────────┘ └─────────┘ └──────────┘ └──────────────┘
```

### Endpoints de la API

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/ask` | Consulta directa al LLM con provider elegido |
| GET | `/health` | Estado del servicio y providers disponibles |
| GET | `/docs` | Swagger UI automático |
| GET | `/metrics` | Métricas Prometheus |

### Cache Redis en la API

Cada llamada a `/ask` genera una clave `MD5(prompt + system + provider)`.
Si esa clave existe en Redis, responde instantáneamente sin llamar al LLM.

```python
# Lógica de cache en langchain-api/main.py
cache_key = hashlib.md5(f"{prompt}{system}{provider}".encode()).hexdigest()

cached = redis_client.get(cache_key)
if cached:
    return {"response": cached, "cached": True}

# Si no hay cache: llamar al LLM
response = await llm_adapter.ask(prompt, system)
redis_client.setex(cache_key, 3600, response)  # TTL: 1 hora
return {"response": response, "cached": False}
```

---

## 5. Modelo de datos

### Tabla `ss_tickets` (resultados del clasificador)

```sql
CREATE TABLE IF NOT EXISTS ss_tickets (
  id                  SERIAL PRIMARY KEY,
  texto               TEXT NOT NULL,
  dominio             VARCHAR(50),           -- IT | cliente | operaciones | otro (configurable)
  categoria           VARCHAR(255),          -- Categoría canónica (corregida por fuzzy matching)
  categoria_propuesta VARCHAR(255),          -- Sugerencia original del LLM (null si match exacto)
  requiere_revision   BOOLEAN DEFAULT FALSE, -- True si la categoría no está en la lista configurada
  prioridad           VARCHAR(10),           -- alta | media | baja
  confianza           FLOAT,                 -- 0.0 a 1.0 (certeza del LLM)
  origen              VARCHAR(50) DEFAULT 'webhook',  -- webhook | gmail | slack | email | manual
  remitente           VARCHAR(255),          -- Email del remitente (solo para origen=gmail)
  alerta              TEXT,                  -- Mensaje generado post-clasificación
  created_at          TIMESTAMP DEFAULT NOW()
);
```

### Tabla `ss_agent_runs` (trazabilidad de ejecuciones)

```sql
CREATE TABLE IF NOT EXISTS ss_agent_runs (
  id              SERIAL PRIMARY KEY,
  run_id          UUID DEFAULT gen_random_uuid(),
  ticket_id       INTEGER REFERENCES ss_tickets(id),
  iterations_used INTEGER,          -- Cuántos ciclos classify→validate usó el agente
  validated       BOOLEAN,          -- Si terminó con clasificación válida
  provider_usado  VARCHAR(50),      -- ollama | openai | anthropic | gemini
  resultado       JSONB,            -- JSON completo de la clasificación
  duracion_ms     INTEGER,          -- Tiempo total de la ejecución en ms
  fecha           TIMESTAMP DEFAULT NOW()
);
```

### Tabla `ss_documentos` (RAG — Fase P5, pendiente)

```sql
-- Requiere extensión pgvector en PostgreSQL
-- Activar con: podman exec postgres psql -U admin -d ai -c "CREATE EXTENSION IF NOT EXISTS vector;"

CREATE TABLE IF NOT EXISTS ss_documentos (
  id        SERIAL PRIMARY KEY,
  contenido TEXT,
  embedding vector(768),    -- Embeddings para búsqueda semántica
  metadata  JSONB,
  fecha     TIMESTAMP DEFAULT NOW()
);
```

### Consultas útiles de operación

```sql
-- Tickets del día por dominio y prioridad
SELECT dominio, prioridad, COUNT(*) as total
FROM ss_tickets
WHERE fecha >= CURRENT_DATE
GROUP BY dominio, prioridad
ORDER BY dominio, prioridad;

-- Tasa de éxito del agente (iteraciones usadas)
SELECT
  iterations_used,
  COUNT(*) as ejecuciones,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as porcentaje
FROM ss_agent_runs
GROUP BY iterations_used
ORDER BY iterations_used;

-- Tickets de alta prioridad sin atender (último día)
SELECT id, dominio, categoria, texto, fecha
FROM ss_tickets
WHERE prioridad = 'alta'
  AND fecha >= NOW() - INTERVAL '24 hours'
ORDER BY fecha DESC;

-- Performance por provider
SELECT provider_usado, AVG(duracion_ms) as avg_ms, COUNT(*) as total
FROM ss_agent_runs
WHERE validated = true
GROUP BY provider_usado;
```

---

## 6. Observabilidad — Prometheus, Grafana, Loki

### Flujo de métricas

```
Servicios                    Prometheus                  Grafana
─────────                    ──────────                  ───────
langchain-agent:8001/metrics ──► scrape c/15s ──────────► dashboards
langchain-api:8000/metrics   ──►
ollama:11434/metrics         ──►
node-exporter:9100/metrics   ──►
```

### Métricas del agente (Prometheus)

```
# Contadores
agent_runs_total{origen="webhook", status="success"}
agent_runs_total{origen="gmail", status="error"}

# Histogramas
agent_iterations_histogram_bucket{le="1"}   # Clasificados en 1 intento
agent_iterations_histogram_bucket{le="3"}   # En máximo 3 intentos
agent_llm_latency_seconds_bucket            # Latencia de llamadas al LLM

# Gauges
agent_validation_failures_total             # Total de fallos de validación
agent_cache_hit_total                       # Total de cache hits en Redis
```

### prometheus.yml — configuración del proyecto

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'langchain-agent'
    static_configs:
      - targets: ['langchain-agent:8001']

  - job_name: 'langchain-api'
    static_configs:
      - targets: ['langchain-api:8000']

  - job_name: 'ollama'
    static_configs:
      - targets: ['ollama:11434']

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
```

### promtail.yml — adaptado para Podman rootless en WSL2

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: containers
    static_configs:
      - targets: [localhost]
        labels:
          job: containers
          __path__: /var/log/pods/*/*/*.log
    pipeline_stages:
      - json:
          expressions:
            stream: stream
            log: log
      - labels:
          stream:
      - output:
          source: log
```

### LangSmith — configuración

```bash
# En .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=tu_key_de_langsmith
LANGCHAIN_PROJECT=shared-services-classifier-dev   # dev / prod
```

Con LangGraph, las trazas en LangSmith muestran:

| Dato | Descripción |
|---|---|
| Graph execution | Todos los nodos ejecutados en orden |
| Node: classify | Input/output de la llamada al LLM + latencia |
| Node: validate | Resultado de validación Pydantic (ok / error) |
| Node: save | Confirmación de inserción en PostgreSQL |
| Iteraciones | Cuántos ciclos classify→validate se ejecutaron |
| Estado completo | El `AgentState` en cada transición |

---

## 7. Red interna Podman

### Reglas de comunicación entre servicios

| Desde | Hacia | Hostname correcto |
|---|---|---|
| langchain-agent | langchain-api | `langchain-api:8000` |
| langchain-agent | postgres | `postgres:5432` |
| langchain-agent | redis | `redis:6379` |
| langchain-api | ollama | `ollama:11434` |
| langchain-api | redis | `redis:6379` |
| prometheus | langchain-agent | `langchain-agent:8001` |
| prometheus | langchain-api | `langchain-api:8000` |
| prometheus | node-exporter | `node-exporter:9100` |
| promtail | loki | `loki:3100` |
| grafana | prometheus | `prometheus:9090` |
| grafana | loki | `loki:3100` |

### Diferencia Docker vs Podman rootless

```bash
# Docker
Socket:      /var/run/docker.sock
Logs:        /var/lib/docker/containers/

# Podman rootless (WSL2)
Socket:      /run/user/$UID/podman/podman.sock
Logs pods:   /var/log/pods/

# Variable de entorno para compatibilidad
export DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock
```

---

## 8. Variables de entorno — referencia completa

### Estado de configuración

| Variable | Valor de desarrollo | Estado |
|---|---|---|
| `LANGCHAIN_TRACING_V2` | `true` | ✅ Configurado |
| `LANGCHAIN_API_KEY` | `lsv2_pt_...` (nueva key) | ✅ Configurado |
| `LANGCHAIN_PROJECT` | `shared-services-classifier-dev` | ✅ Actualizado |
| `AGENT_PROVIDER` | `ollama` | ✅ Default dev |
| `AGENT_MAX_ITERATIONS` | `5` | ✅ Por defecto |
| `AGENT_DOMAINS` | `IT,cliente,operaciones,otro` | ✅ Configurable |
| `OPENAI_API_KEY` | `sk-proj-...` (nueva key) | ✅ Configurado |
| `ANTHROPIC_API_KEY` | — | ❌ Pendiente |
| `GEMINI_API_KEY` | — | ❌ Pendiente |

### Todas las variables de `env.txt`

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=tu_langsmith_key
LANGCHAIN_PROJECT=shared-services-classifier-dev

AGENT_PROVIDER=ollama
AGENT_MAX_ITERATIONS=5
VALIDATION_ENABLED=true
AGENT_DOMAINS=IT,cliente,operaciones,otro

OPENAI_API_KEY=tu_openai_key
ANTHROPIC_API_KEY=tu_anthropic_key
GEMINI_API_KEY=tu_gemini_key

OLLAMA_MODEL=llama3.2:3b
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
GEMINI_MODEL=gemini-1.5-flash

POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=ai

REDIS_HOST=redis
REDIS_PORT=6379

GRAFANA_PASSWORD=admin
AGENT_HOST=0.0.0.0
AGENT_PORT=8001
```

---

## 9. Dependencias Python

### `langchain-agent/requirements.txt`

```
# Framework web
fastapi
uvicorn

# LangChain + LangGraph
langchain
langchain-core
langgraph              # Orquestación del agente con grafo de estados

# Validación y estado
pydantic               # Schema del ticket + validación del AgentState

# Base de datos async
asyncpg                # Conexión async a PostgreSQL

# HTTP cliente async
httpx                  # Llamadas entre servicios (agente → API)

# Cache y estado
redis                  # Cache LLM + estado del agente entre nodos

# Observabilidad
prometheus-fastapi-instrumentator   # Métricas en /metrics
```

### `langchain-api/requirements.txt`

```
# Framework web
fastapi
uvicorn

# LangChain core + adapters por provider
langchain
langchain-core
langchain-ollama       # Adapter para Ollama
langchain-openai       # Adapter para OpenAI
langchain-anthropic    # Adapter para Anthropic
langchain-google-genai # Adapter para Gemini

# Validación
pydantic

# Cache
redis

# Observabilidad
prometheus-fastapi-instrumentator
```

---

## 10. Workflow del agente — arquitectura detallada

### Flujo completo de procesamiento

```
curl POST http://localhost:8001/process
     │  {"texto": "Error en servidor de producción", "origen": "webhook"}
     │
     ▼
langchain-agent:8001 — FastAPI valida el request (Pydantic)
     │  Crea AgentState con texto, origen, provider, max_iterations
     │  Inicia el grafo LangGraph
     │
     ▼ Nodo: classify (iteración 1)
HTTP POST → langchain-api:8000/ask
     │  provider=ollama
     │  prompt=texto
     │  system=SYSTEM_PROMPT (con dominios dinámicos del .env)
     │
     │  Verifica cache Redis (MD5 del prompt+system+provider)
     │    ├── Cache HIT  → respuesta en <100ms (cached=true)
     │    └── Cache MISS → llama a Ollama (~25s) → guarda en Redis
     │
     │  Recibe: {"dominio":"IT","categoria":"incidente","prioridad":"alta","confianza":0.95}
     │
     ▼ Nodo: validate
Pydantic ClasificacionSchema(**classification)
     │  ✅ OK → state.validated = True → continúa a save
     │  ❌ Error → state.error = mensaje → vuelve a classify
     │             (máximo AGENT_MAX_ITERATIONS veces)
     │
     ▼ Nodo: save
INSERT INTO ss_tickets (texto, dominio, categoria, prioridad, confianza, origen, remitente, alerta)
     │  VALUES ('Error en servidor...', 'IT', 'incidente', 'alta', 0.95, 'webhook', null, 'URGENTE: ...')
     │
INSERT INTO ss_agent_runs (ticket_id, iterations_used, validated, provider_usado, resultado, duracion_ms)
     │  VALUES (ticket_id, 1, true, 'ollama', {...}, 26430)
     │
     ▼
Response 200: {dominio, categoria, prioridad, confianza, alerta, iterations_used: 1, validated: true}
```

### Flujo Gmail (origen email)

```
Gmail llega a la bandeja de entrada
     │  (configurado con Gmail Trigger o webhook de Gmail)
     │
     ▼
POST http://localhost:8001/process
     │  {
     │    "texto": "snippet del email",
     │    "origen": "gmail",
     │    "remitente": "usuario@empresa.com"
     │  }
     │
     ▼ [mismo flujo de classify → validate → save]
     │
     ▼ Post-clasificación: generar respuesta al remitente
Si prioridad = "alta":
  subject: "Tu ticket fue recibido - Prioridad ALTA"
  body: "Tu ticket ha sido clasificado. Categoría: X. Un agente te contactará pronto."
Si prioridad != "alta":
  subject: "Tu ticket fue recibido - En proceso"
  body: "Tu ticket ha sido clasificado con prioridad Y."
```

---

## 11. Migración desde n8n — equivalencias

### Tabla de equivalencias

| n8n (anterior) | LangChain Agent (ahora) |
|---|---|
| Webhook trigger | `POST /process` endpoint en FastAPI |
| Gmail trigger | Webhook Gmail → `POST /process` con `origen=gmail` |
| Edit Fields (extraer texto) | `AgentState.texto` — campo del request |
| HTTP Request a langchain-api | `classify_node` — llamada HTTP async con httpx |
| Code node (parsear JSON) | `validate_node` — validación Pydantic |
| IF node (prioridad alta/baja) | `should_retry()` router del grafo LangGraph |
| Postgres Insert | `save_node` — INSERT con asyncpg |
| Send Gmail | Tool de email (a agregar como Tool en el agente) |
| catch silencioso en JS | Retry automático con instrucciones ajustadas |

### Flujo n8n vs LangGraph

```
n8n (estático, sin retry):
  Webhook/Gmail → Edit Fields → HTTP Request → Code → IF → Postgres → Gmail

LangChain Agent (dinámico, con retry autónomo):
  /process → [classify → validate → ¿retry?] × N → save → response
                   ↑________________________↓
                    Loop con decisión autónoma
                    máx AGENT_MAX_ITERATIONS veces
```

---

## 12. Roadmap de evolución

| Fase | Descripción | Estado |
|---|---|---|
| **Fase 1** | Setup WSL2 + estructura base + stack levantado | 🎯 Actual |
| **Fase 2** | `langchain-api`: FastAPI + 4 providers + Redis cache | Pendiente |
| **Fase 3** | `langchain-agent`: LangGraph classify→validate→save | Pendiente |
| **Fase 4** | Observabilidad: dashboards Grafana + Loki + LangSmith | Pendiente |
| **Fase 5** | Hardening: auth en `/process`, rate limiting, HTTPS | Pendiente |
| **Fase 6** | Producción: MV Unix / AWS | Pendiente |
| **P5** | RAG: pgvector + embeddings + multi-agente LangGraph | Futuro |

---

*shared-services-classifier · Arquitectura Técnica · Marzo 2026*
