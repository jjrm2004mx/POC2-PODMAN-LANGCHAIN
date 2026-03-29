# AI Stack for Dummies
## shared-services-classifier · Versión 5.0
**Incluye: LangChain Agent · LangGraph · Podman · Redis · Prometheus · Grafana · Loki · LangSmith**
**Marzo 2026**

---

## La analogía: tu stack es una empresa de clasificación postal

Imagina una oficina que recibe cartas de muchos departamentos de la empresa
y las clasifica automáticamente para que lleguen al lugar correcto.

| Pieza de la empresa postal | Pieza de tu stack |
|---|---|
| La ventanilla que recibe cartas | LangChain Agent (clasificador principal) |
| El catálogo de reglas de clasificación | LangGraph (el cerebro que decide) |
| El experto que lee y clasifica | Ollama / OpenAI / Anthropic / Gemini |
| El archivero que guarda copias | PostgreSQL |
| La memoria rápida de cartas frecuentes | Redis (caché) |
| El edificio que contiene todo | Podman (contenedores) |
| El auditor de calidad | Pydantic (valida que la clasificación sea correcta) |
| El inspector de operaciones | Prometheus + Grafana + Node Exporter |
| El diario de incidentes | Loki + Promtail (logs centralizados) |
| El supervisor externo de IA | LangSmith (trazabilidad del agente) |

---

## Estado actual del stack

Todos los servicios corren con `podman-compose` desde `~/podman/ai-stack`.

| Componente | Imagen / Build | Puerto | Rol |
|---|---|---|---|
| langchain-agent | build local | 8001 | 🎯 Núcleo del proyecto |
| langchain-api | build local | 8000 | Gateway de IA |
| Ollama | ollama/ollama | 11434 | IA local |
| PostgreSQL | postgres:15 | 5432 | Base de datos |
| Redis | redis:7-alpine | 6379 | Cache + estado del agente |
| Prometheus | prom/prometheus | 9090 | Métricas |
| Grafana | grafana/grafana | 3000 | Dashboards |
| Node Exporter | prom/node-exporter | 9100 | Métricas del host |
| Loki | grafana/loki:2.9.0 | 3100 | Logs centralizados |
| Promtail | grafana/promtail | — | Recolector de logs |
| LangSmith | cloud | — | Trazas del agente |

**Providers de IA disponibles:**

| Provider | Modelo | Tipo | Estado |
|---|---|---|---|
| Ollama | llama3.2:3b | Local, sin costo, sin internet | ✅ Default en desarrollo |
| OpenAI | gpt-4o-mini | Cloud | 🔑 Requiere API key |
| Anthropic | claude-3-5-haiku-20241022 | Cloud | 🔑 Requiere API key |
| Gemini | gemini-1.5-flash | Cloud | 🔑 Requiere API key |

---

## Podman — El edificio

Podman empaqueta cada componente en un **contenedor**: una caja sellada que
incluye el programa y todo lo que necesita. Si algo falla dentro de una caja,
no afecta a las demás.

La diferencia clave con Docker es que Podman es **rootless**: no necesita
un proceso administrador corriendo con permisos de root. Es más seguro y
genera contenedores compatibles con Kubernetes nativamente.

```bash
# Mismos comandos que Docker, diferente runtime
docker compose up -d    →    podman-compose up -d
docker compose down     →    podman-compose down
docker ps               →    podman ps
docker logs nombre      →    podman logs nombre
docker exec             →    podman exec
```

> **Regla de oro de comunicación entre contenedores:**
> Dentro de Podman los servicios se hablan por **nombre del servicio**,
> nunca por `localhost`.
>
> ✅ Correcto: `http://langchain-api:8000`
> ❌ Incorrecto: `http://localhost:8000`

---

## LangChain Agent — El clasificador inteligente (núcleo del proyecto)

Este es el corazón del sistema. Recibe un ticket de cualquier fuente
y lo clasifica de forma autónoma usando un **loop dinámico con decisión propia**.

### ¿Qué entradas acepta?

| Origen | Cómo llega | Campo clave |
|---|---|---|
| Webhook / HTTP | `POST http://localhost:8001/process` | `body.texto` |
| Gmail | Trigger automático al llegar un email | snippet del mensaje |
| Slack, otros | Webhook configurado | campo `texto` |

### ¿Qué hace paso a paso?

```
Ticket entra
     │
     ▼
[classify] ── Llama al LLM con el texto del ticket
     │         El LLM responde con JSON:
     │         { dominio, categoria, prioridad, confianza }
     ▼
[validate] ── ¿El JSON tiene formato correcto?
     │         ¿Los valores son válidos según el schema?
     │    ❌ No → vuelve a [classify] con instrucciones ajustadas
     │             (máximo 5 intentos)
     │    ✅ Sí → continúa
     ▼
[save] ─────── Guarda en PostgreSQL (tabla ss_tickets)
     │         Registra la ejecución (tabla ss_agent_runs)
     │         Genera alerta según prioridad
     ▼
Responde con el resultado completo al cliente
```

### ¿Qué devuelve?

```json
{
  "run_id": "abc-123-uuid",
  "dominio": "IT",
  "categoria": "incidente",
  "prioridad": "alta",
  "confianza": 0.95,
  "alerta": "URGENTE: ticket de incidente con prioridad alta",
  "texto_original": "El servidor de producción no responde desde las 9am",
  "origen": "webhook",
  "iterations_used": 1,
  "cached": false,
  "validated": true
}
```

### ¿Por qué es mejor que el flujo n8n anterior?

| n8n (anterior) | LangChain Agent (ahora) |
|---|---|
| JSON malformado del LLM → fallo silencioso | Falla → reintenta automáticamente con instrucciones corregidas |
| Categorías fijas hardcodeadas en el flujo | Dominios configurables vía variable de entorno |
| Lógica en nodos visuales JSON (difícil de versionar en Git) | Código Python puro, 100% Git-friendly |
| Flujo estático A → B → C | Loop dinámico: el agente decide cuándo avanzar |
| Sin validación de esquema de salida | Validación Pydantic obligatoria antes de guardar |
| 1 origen (webhook o gmail, no ambos a la vez) | Multi-origen: webhook, gmail, slack, manual |

---

## LangGraph — El cerebro que orquesta

LangGraph es la librería que define el **grafo de decisión** del agente.
Es como un diagrama de flujo con memoria y lógica dinámica.

```
     ┌─────────────────────────────────────────┐
     │            LangGraph Agent              │
     │                                         │
     │  ┌──────────┐   ┌──────────┐            │
     │  │ classify │──▶│ validate │            │
     │  └──────────┘   └────┬─────┘            │
     │       ▲              │                  │
     │       │         ┌────▼──────┐           │
     │       │    ❌    │  ¿válido? │           │
     │       └─────────│   No      │           │
     │      retry      └────┬──────┘           │
     │    (máx 5)           │ ✅ Sí             │
     │                 ┌────▼──────┐           │
     │                 │   save    │           │
     │                 └───────────┘           │
     └─────────────────────────────────────────┘
```

Cada vez que el agente regresa a `classify`, puede **modificar el prompt**
para guiar al LLM hacia una respuesta correcta. Esto es lo que hace al
sistema **autónomo**: no solo ejecuta pasos fijos, sino que decide cómo
proceder en función del resultado de cada paso.

---

## LangChain API — La cocina (gateway de IA)

FastAPI expone los modelos de IA como API REST. El patrón
**Adapter + Strategy** permite intercambiar el proveedor de IA con un solo
campo en el JSON, sin tocar código ni reiniciar el stack.

```
LangChain Agent  →  langchain-api:8000  →  Provider elegido
                                              ├── Ollama (local)
                                              ├── OpenAI
                                              ├── Anthropic
                                              └── Gemini
```

**Cambiar provider en un request (sin reiniciar nada):**

```bash
# Default: Ollama (local, sin costo)
curl -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"texto": "El servidor no responde", "origen": "webhook"}'

# Cambiar a OpenAI para este request
curl -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"texto": "El servidor no responde", "origen": "webhook", "provider": "openai"}'

# Providers disponibles: ollama | openai | anthropic | gemini
```

---

## Ollama — El chef de IA local

Corre modelos de inteligencia artificial **dentro de tu servidor**,
sin internet, sin costo por uso y con privacidad total.

**Modelo instalado:** `llama3.2:3b` (2 GB, ideal para clasificación de texto)

| Ventaja | Desventaja |
|---|---|
| Privacidad total — datos no salen del servidor | Lento en CPU: 15-40 segundos por clasificación |
| Sin costo por token | Menos capaz que GPT-4 en tareas complejas |
| Funciona sin internet | Requiere ~3 GB de RAM durante la inferencia |

**URL:** http://localhost:11434

---

## PostgreSQL — El archivero

Base de datos relacional que guarda todos los tickets clasificados y
el historial de ejecuciones del agente.

**Tablas del proyecto:**

| Tabla | Qué guarda |
|---|---|
| `ss_tickets` | Cada ticket: texto, dominio, categoría, prioridad, confianza, origen, remitente, alerta |
| `ss_agent_runs` | Cada ejecución: iteraciones, tiempo, proveedor, resultado completo |

**Nota sobre el prefijo `ss_`:** Las tablas usan el prefijo `ss` (Shared Services)
para coexistir con otras tablas del mismo servidor PostgreSQL sin conflicto.

**Conexión:**

| Parámetro | Valor |
|---|---|
| Host (desde otros contenedores) | `postgres` |
| Host (desde Windows/WSL directo) | `localhost` |
| Puerto | `5432` |
| Base de datos | `ai` |
| Usuario / Password | `admin / admin` |

---

## Redis — La memoria rápida

Redis es una base de datos en memoria ultrarrápida que cumple dos roles:

**Rol 1 — Cache de respuestas LLM:**

```
Primera clasificación:   texto → Ollama → 25 segundos → guarda en Redis
Segunda clasificación:   texto → Redis → 80 milisegundos ← cached: true
```

La clave se genera con MD5 del texto + sistema + provider, con expiración de 1 hora.

**Rol 2 — Estado del agente entre iteraciones:**
El contexto del agente se preserva en Redis entre los nodos del grafo
LangGraph, para que no pierda información entre `classify`, `validate` y `save`.

---

## Dominios configurables — Core de Shared Services

Este sistema está diseñado para clasificar tickets de **múltiples dominios**
operacionales. Los dominios no están fijos en el código — se configuran
en el `.env`:

```bash
# En ~/podman/ai-stack/.env
AGENT_DOMAINS=IT,cliente,operaciones,otro
```

**Agregar un nuevo dominio (ejemplo: RRHH):**

```bash
# 1. Editar .env
cd ~/podman/ai-stack
nano .env
# Cambiar: AGENT_DOMAINS=IT,cliente,operaciones,RRHH,otro

# 2. Reiniciar solo el agente
cd ~/podman/ai-stack
podman-compose restart langchain-agent

# Sin tocar código. Sin modificar la base de datos.
```

**Schema del ticket:**

| Campo | Tipo | Valores posibles |
|---|---|---|
| `dominio` | str | Los definidos en AGENT_DOMAINS |
| `categoria` | str | Libre según dominio (bug, factura, incidente, etc.) |
| `prioridad` | str | `alta` / `media` / `baja` |
| `confianza` | float | 0.0 a 1.0 |

---

## LangSmith — El supervisor de IA

Mientras Grafana monitorea la infraestructura, LangSmith monitorea
la **inteligencia**: cada llamada al LLM queda registrada con input,
output, latencia, número de iteraciones y errores de validación.

```
Ejecución visible en LangSmith:
├── Nodo: classify
│   ├── Input: "El servidor no responde desde las 9am"
│   ├── System: "Eres un clasificador de tickets de Shared Services..."
│   ├── Output: {"dominio":"IT","categoria":"incidente","prioridad":"alta","confianza":0.95}
│   └── Latencia: 23.4s
├── Nodo: validate
│   ├── Resultado: validated=true, 0 errores
│   └── Latencia: 0.002s
└── Nodo: save
    ├── ticket_id: 142 insertado en ss_tickets
    └── Latencia: 0.015s
```

**5 funciones principales de LangSmith:**

| Función | Para qué sirve |
|---|---|
| Tracing | Ver cada ejecución completa nodo por nodo |
| Datasets | Guardar casos de prueba del clasificador |
| Playground | Probar prompts sin tocar código ni reiniciar |
| Evaluations | Medir precisión: ¿clasifica correctamente? |
| Monitoring | Tickets/día, errores, latencia promedio en producción |

**Configuración en `.env`:**

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=tu_key_de_langsmith
LANGCHAIN_PROJECT=shared-services-classifier-dev
```

---

## Prometheus + Grafana + Node Exporter — El inspector

Prometheus recolecta métricas cada 15 segundos. Grafana las muestra
en dashboards interactivos. Node Exporter agrega métricas del servidor.

| Componente | Qué monitorea | URL |
|---|---|---|
| Prometheus | Scraping de todos los servicios | http://localhost:9090 |
| Grafana | Dashboards interactivos | http://localhost:3000 |
| Node Exporter | CPU, RAM, disco, red del host | http://localhost:9100 |

**Métricas clave del agente clasificador:**

```
agent_runs_total              → Total de tickets procesados
agent_iterations_histogram    → Distribución de iteraciones por clasificación
agent_validation_failures     → Fallos de validación Pydantic
agent_llm_calls_total         → Llamadas por provider (ollama, openai...)
http_request_duration_seconds → Latencia de respuesta del endpoint /process
```

**Grafana:** http://localhost:3000 — credenciales: admin / admin

---

## Loki + Promtail — El diario de incidentes

Loki centraliza los logs de todos los contenedores en un solo lugar.
Desde Grafana puedes buscar en todos los logs con consultas LogQL.

**Consultas útiles en Grafana → Explore → Loki:**

```logql
{container="langchain-agent"}                          # Todos los logs del agente
{container="langchain-agent"} |= "validated=true"      # Clasificaciones exitosas
{container="langchain-agent"} |= "validation_failed"   # Errores de validación
{container="langchain-agent"} |= "iterations_used"     # Ver iteraciones
{job="containers"} |= "ERROR"                          # Errores en cualquier servicio
```

---

## El archivo .env — Las llaves del edificio

El archivo `~/podman/ai-stack/.env` contiene todas las configuraciones
secretas y parámetros del sistema.

> ⚠️ **NUNCA subir `.env` a Git.**
> El archivo `env.txt` es la plantilla sin valores reales — ese sí va al repositorio.

**Variables más importantes:**

```bash
# Provider de IA por defecto
AGENT_PROVIDER=ollama          # ollama | openai | anthropic | gemini

# Límite de intentos del loop del agente
AGENT_MAX_ITERATIONS=5

# Dominios del clasificador — agregar sin tocar código
AGENT_DOMAINS=IT,cliente,operaciones,otro
```

---

## Flujo completo del sistema

```
┌────────────────────────────────────────────────────────────┐
│                      PODMAN (WSL2)                          │
│                                                             │
│  Webhook HTTP ─┐                                           │
│  Gmail        ─┤──▶  langchain-agent :8001                 │
│  Slack        ─┘     ┌──────────────────────────────────┐  │
│                       │  LangGraph                       │  │
│                       │  classify → validate → save      │  │
│                       │      ↑_________❌ retry (≤5)     │  │
│                       └──────────────────────────────────┘  │
│                              │                │             │
│                              ▼                ▼             │
│                    langchain-api :8000    redis :6379        │
│                    ┌───────────────┐    (cache + estado)    │
│                    │ Ollama :11434 │                        │
│                    │ OpenAI cloud  │                        │
│                    │ Anthropic cloud│                       │
│                    │ Gemini cloud  │                        │
│                    └───────────────┘                        │
│                                                             │
│                    postgres :5432                           │
│                    ss_tickets | ss_agent_runs               │
│                                                             │
│  prometheus :9090 │ grafana :3000 │ loki :3100              │
└────────────────────────────────────────────────────────────┘
              │
       LangSmith (cloud) ← trazas de cada ejecución del agente
```

---

## Portabilidad — De WSL2 a producción

El mismo stack que corre en tu laptop WSL2 se despliega en
una MV Unix o AWS con solo 4 comandos:

```bash
git clone https://github.com/jjrm2004mx/POC2-PODMAN-LANGCHAIN.git ~/podman/ai-stack
cd ~/podman/ai-stack
cp env.txt .env
nano .env          # Completar con keys reales de producción
podman-compose up -d
```

La diferencia entre ambientes vive únicamente en el `.env`.

---

## Referencia rápida de URLs

| Servicio | URL | Credenciales |
|---|---|---|
| LangChain Agent | http://localhost:8001 | — |
| Agent Docs (Swagger) | http://localhost:8001/docs | — |
| LangChain API | http://localhost:8000 | — |
| API Docs (Swagger) | http://localhost:8000/docs | — |
| Ollama | http://localhost:11434 | — |
| PostgreSQL | localhost:5432 | admin / admin / db: ai |
| Redis | localhost:6379 | sin auth |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Node Exporter | http://localhost:9100 | — |
| Loki | http://localhost:3100 | — |
| LangSmith | https://smith.langchain.com | cuenta Google |

---

*shared-services-classifier · AI Stack for Dummies v5.0 · Marzo 2026*
