# 00 — Setup WSL + Windows
## shared-services-classifier · Instalación desde cero
**Ruta raíz del proyecto: `~/podman/ticket-classification`**
**Marzo 2026**

---

## Índice

1. [Prerrequisitos Windows](#1-prerrequisitos-windows)
2. [Instalar WSL2 con Ubuntu 22.04](#2-instalar-wsl2-con-ubuntu-2204)
3. [Configurar el sistema Ubuntu](#3-configurar-el-sistema-ubuntu)
4. [Instalar Podman](#4-instalar-podman)
5. [Instalar podman-compose](#5-instalar-podman-compose)
6. [Crear estructura del proyecto](#6-crear-estructura-del-proyecto)
7. [Clonar el repositorio](#7-clonar-el-repositorio)
8. [Configurar variables de entorno](#8-configurar-variables-de-entorno)
9. [Adaptar archivos de configuración para Podman](#9-adaptar-archivos-de-configuración-para-podman)
10. [Primer arranque del stack](#10-primer-arranque-del-stack)
11. [Verificar que todo funciona](#11-verificar-que-todo-funciona)
12. [Comandos de uso diario](#12-comandos-de-uso-diario)
13. [Troubleshooting inicial](#13-troubleshooting-inicial)
14. [Referencia rápida de puertos](#14-referencia-rápida-de-puertos)

---

## 1. Prerrequisitos Windows

**Abrir PowerShell como Administrador:**

```powershell
# Verificar versión de Windows
# Necesitas: Windows 10 build 19041+ o Windows 11
winver
```

**Requisitos mínimos de hardware:**

| Recurso | Mínimo | Recomendado |
|---|---|---|
| RAM | 8 GB | 16 GB (Ollama consume ~3 GB en inferencia) |
| Disco libre | 20 GB | 40 GB |
| CPU | 4 núcleos | 8 núcleos |
| Virtualización | Intel VT-x o AMD-V habilitado en BIOS | — |

**Verificar que la virtualización esté habilitada:**

```powershell
# En PowerShell como Administrador
Get-ComputerInfo -Property HyperVisorPresent
# Resultado esperado:  HyperVisorPresent : True
# Si muestra False → entrar al BIOS y habilitar Intel VT-x o AMD-V
```

---

## 2. Instalar WSL2 con Ubuntu 22.04

**En PowerShell como Administrador:**

```powershell
# Instalar WSL2 con Ubuntu 22.04
wsl --install -d Ubuntu-22.04

# Si ya tienes WSL instalado, asegurarse de usar versión 2
wsl --set-default-version 2

# Verificar la instalación (después de reiniciar Windows)
wsl --list --verbose
# Resultado esperado:
#   NAME            STATE    VERSION
#   Ubuntu-22.04    Running  2
```

> Después de la instalación **reiniciar Windows**. Al abrir Ubuntu por
> primera vez se pedirá crear usuario y contraseña — este será tu usuario WSL.

> Si ya tienes Ubuntu en WSL1, convertir:
> ```powershell
> wsl --set-version Ubuntu-22.04 2
> ```

---

## 3. Configurar el sistema Ubuntu

**Abrir la terminal de Ubuntu (desde menú inicio o ejecutando `wsl` en PowerShell):**

```bash
# Actualizar paquetes del sistema
sudo apt update && sudo apt upgrade -y

# Instalar herramientas base esenciales
sudo apt install -y \
  curl \
  git \
  wget \
  build-essential \
  python3 \
  python3-pip \
  python3-venv \
  jq \
  nano \
  tree \
  net-tools \
  ca-certificates \
  gnupg \
  lsb-release

# Verificar Python (debe ser 3.10+)
python3 --version

# Configurar Git
git config --global user.name "jjrm2004mx"
git config --global user.email "tu-email@ejemplo.com"
git config --global init.defaultBranch main

# Verificar configuración
git config --list
```

---

## 4. Instalar Podman

```bash
# Agregar repositorio oficial de Podman para Ubuntu 22.04
sudo mkdir -p /etc/apt/keyrings

curl -fsSL https://download.opensuse.org/repositories/devel:kubic:libcontainers:stable/xUbuntu_22.04/Release.key \
  | gpg --dearmor \
  | sudo tee /etc/apt/keyrings/libcontainers-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/libcontainers-archive-keyring.gpg] \
  https://download.opensuse.org/repositories/devel:kubic:libcontainers:stable/xUbuntu_22.04/ /" \
  | sudo tee /etc/apt/sources.list.d/devel:kubic:libcontainers:stable.list

sudo apt update
sudo apt install -y podman

# Verificar instalación
podman --version
# Resultado esperado: podman version 4.x.x
```

**Configurar Podman en modo rootless:**

```bash
# Verificar que el usuario tenga subUIDs asignados
cat /etc/subuid | grep $USER
# Si no aparece nada, asignar rangos:
sudo usermod --add-subuids 100000-165535 $USER
sudo usermod --add-subgids 100000-165535 $USER

# Aplicar configuración rootless
podman system migrate

# Prueba de funcionamiento
podman run --rm hello-world
# Debe imprimir: "Hello from Docker!" — Podman funciona correctamente
```

**Habilitar el socket de Podman:**

```bash
# Habilitar y arrancar el socket para el usuario actual
systemctl --user enable podman.socket
systemctl --user start podman.socket

# Verificar estado
systemctl --user status podman.socket
# Resultado esperado: Active: active (listening)

# Configurar variable DOCKER_HOST para compatibilidad con Promtail
echo 'export DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock' >> ~/.bashrc
source ~/.bashrc

# Verificar
echo $DOCKER_HOST
# Resultado: unix:///run/user/1000/podman/podman.sock
```

> **¿Por qué Podman en lugar de Docker?**
> Podman es rootless (sin daemon privilegiado), más seguro,
> y genera pods compatibles con Kubernetes nativamente.
> Usa el mismo `docker-compose.yml` pero con `podman-compose`.

---

## 5. Instalar podman-compose

```bash
# Instalar via pip3
pip3 install podman-compose

# Agregar pip local al PATH si no está ya
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc

# Verificar instalación
podman-compose --version
# Resultado esperado: podman-compose version 1.x.x
```

> **Importante:** podman-compose lee el archivo `docker-compose.yml` por
> defecto — el mismo nombre que Docker Compose. No cambia el nombre del
> archivo, solo el comando: `docker-compose` → `podman-compose`.

---

## 6. Crear estructura del proyecto

```bash
# Crear carpeta base
mkdir -p ~/podman
cd ~/podman
pwd
# Resultado: /home/TU_USUARIO/podman
```

**Estructura completa esperada:**

```
~/podman/ticket-classification/                         ← RAÍZ DEL PROYECTO
├── docker-compose.yml                     ← Definición de todos los servicios
├── .env                                   ← Variables secretas (NO subir a Git)
├── env.txt                                ← Plantilla del .env (SÍ en Git)
├── prometheus.yml                         ← Config scraping de métricas
├── promtail.yml                           ← Config recolección de logs
├── .gitignore
├── README.md
├── docs/                                  ← Documentación del proyecto
│   ├── 00_setup_wsl_windows.md
│   ├── 01_ai_stack_for_dummies.md
│   ├── 02_arquitectura_tecnica.md
│   └── 03_guia_operacional.md
├── langchain-agent/                       ← Orquestador LangGraph (núcleo)
│   ├── agent.py                           ← Grafo: classify→validate→save
│   ├── main.py                            ← FastAPI endpoint /process
│   ├── requirements.txt
│   └── Dockerfile
├── langchain-api/                         ← Gateway FastAPI + Adapter+Strategy
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── n8n-workflows/                         ← Backup flujos n8n (referencia)
│   └── POC2_-_Clasificador_de_tickets.json
├── postgres_data/                         ← Volumen PostgreSQL (NO en Git)
├── ollama_data/                           ← Modelos Ollama (NO en Git)
├── grafana_data/                          ← Dashboards Grafana (NO en Git)
└── redis_data/                            ← Datos Redis (NO en Git)
```

**Crear el `.gitignore`:**

```bash
cat > ~/podman/ticket-classification/.gitignore << 'EOF'
# Volúmenes de contenedores — datos persistentes
postgres_data/
ollama_data/
grafana_data/
n8n_data/
redis_data/
loki_data/

# Variables de entorno con secrets
.env

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs locales
*.log
EOF
```

---

## 7. Clonar el repositorio

```bash
cd ~/podman

# Clonar el repositorio en la carpeta ticket-classification
git clone https://github.com/jjrm2004mx/POC2-PODMAN-LANGCHAIN.git ticket-classification

# Entrar al proyecto — ESTA ES TU RUTA RAÍZ SIEMPRE
cd ~/podman/ticket-classification

# Verificar estado del repo
git status
git log --oneline -5

# Ver estructura
tree ~/podman/ticket-classification -L 2
```

**Si el repositorio está vacío y necesitas inicializar:**

```bash
cd ~/podman/ticket-classification

# Crear directorios
mkdir -p docs langchain-agent langchain-api n8n-workflows
mkdir -p postgres_data ollama_data grafana_data redis_data

# Primer commit
git add .gitignore env.txt README.md
git commit -m "chore: inicializar estructura del proyecto"
git push origin main
```

---

## 8. Configurar variables de entorno

```bash
cd ~/podman/ticket-classification

# Copiar plantilla
cp env.txt .env

# Editar con nano
nano ~/podman/ticket-classification/.env
```

**Contenido completo del `.env` para desarrollo en WSL:**

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# shared-services-classifier — Variables de entorno
# Ambiente: desarrollo (WSL2)
# NUNCA subir este archivo a Git
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── LangSmith (trazabilidad del agente) ──────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=tu_nueva_langsmith_key_aqui
LANGCHAIN_PROJECT=shared-services-classifier-dev

# ── Agente ───────────────────────────────────────
AGENT_PROVIDER=ollama
AGENT_MAX_ITERATIONS=5
VALIDATION_ENABLED=true
# Dominios configurables — separados por coma, sin espacios
AGENT_DOMAINS=IT,cliente,operaciones,otro

# ── Providers de IA cloud ─────────────────────────
OPENAI_API_KEY=tu_nueva_openai_key_aqui
ANTHROPIC_API_KEY=tu_anthropic_key_aqui
GEMINI_API_KEY=tu_gemini_key_aqui

# ── Modelos por provider ──────────────────────────
OLLAMA_MODEL=llama3.2:3b
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
GEMINI_MODEL=gemini-1.5-flash

# ── PostgreSQL ────────────────────────────────────
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=ai

# ── Redis ─────────────────────────────────────────
REDIS_HOST=redis
REDIS_PORT=6379

# ── Observabilidad ────────────────────────────────
GRAFANA_PASSWORD=admin

# ── Servicio del agente ───────────────────────────
AGENT_HOST=0.0.0.0
AGENT_PORT=8001
```

**Crear `env.txt` — plantilla para Git (sin keys reales):**

```bash
cat > ~/podman/ticket-classification/env.txt << 'EOF'
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# shared-services-classifier — Plantilla de variables
# cp env.txt .env  y completar con valores reales
# NUNCA subir .env a Git
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
EOF
```

---

## 9. Adaptar archivos de configuración para Podman

### prometheus.yml — Agregar scrape del agente

El stack anterior monitoreaba `langchain-api` pero no el nuevo `langchain-agent`.
Reemplazar con la versión completa:

```bash
cat > ~/podman/ticket-classification/prometheus.yml << 'EOF'
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
EOF
```

### promtail.yml — Adaptar para Podman rootless en WSL2

El archivo original usa `/var/lib/docker/containers` y `/var/run/docker.sock`
(rutas de Docker). Podman rootless en WSL2 usa rutas distintas:

```bash
cat > ~/podman/ticket-classification/promtail.yml << 'EOF'
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
      - targets:
          - localhost
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
EOF
```

> **Nota WSL2 + Podman rootless:** Los logs de contenedores se encuentran en
> `/var/log/pods/`. Si no aparecen logs en Loki verificar la ruta exacta con:
> `podman inspect langchain-agent --format '{{.LogPath}}'`

---

## 10. Primer arranque del stack

### Paso 1 — Descargar el modelo Ollama (solo la primera vez, ~2 GB)

```bash
cd ~/podman/ticket-classification

# Levantar solo Ollama
podman-compose up -d ollama

# Esperar a que arranque
sleep 20

# Descargar el modelo (puede tardar varios minutos según velocidad de internet)
podman exec -it ollama ollama pull llama3.2:3b

# Verificar descarga exitosa
podman exec -it ollama ollama list
# Resultado esperado:
# NAME           ID            SIZE   MODIFIED
# llama3.2:3b    ...           2.0 GB ...
```

### Paso 2 — Crear tablas en PostgreSQL (solo la primera vez)

```bash
cd ~/podman/ticket-classification

# Levantar PostgreSQL
podman-compose up -d postgres
sleep 15

# Crear las tablas del proyecto
podman exec -it postgres psql -U admin -d ai << 'SQL'

CREATE TABLE IF NOT EXISTS ss_tickets (
  id          SERIAL PRIMARY KEY,
  texto       TEXT NOT NULL,
  dominio     VARCHAR(50),
  categoria   VARCHAR(50),
  prioridad   VARCHAR(20),
  confianza   FLOAT,
  origen      VARCHAR(30) DEFAULT 'webhook',
  remitente           VARCHAR(255),
  nombre_remitente    VARCHAR(255),
  alerta      TEXT,
  fecha       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ss_agent_runs (
  id              SERIAL PRIMARY KEY,
  run_id          UUID DEFAULT gen_random_uuid(),
  ticket_id       INTEGER REFERENCES ss_tickets(id),
  iterations_used INTEGER,
  validated       BOOLEAN,
  provider_usado  VARCHAR(50),
  resultado       JSONB,
  duracion_ms     INTEGER,
  fecha           TIMESTAMP DEFAULT NOW()
);

\dt ss_*
SQL
# Debe mostrar:
#          List of relations
#  Schema |     Name      | Type  |
# --------+---------------+-------+
#  public | ss_agent_runs | table |
#  public | ss_tickets    | table |
```

### Paso 3 — Levantar el stack completo

```bash
cd ~/podman/ticket-classification

# Levantar todos los servicios en background
podman-compose up -d

# Ver estado de todos los contenedores
podman ps

# Ver logs en tiempo real (Ctrl+C para salir)
podman-compose logs -f
```

---

## 11. Verificar que todo funciona

Esperar **60 segundos** después del `up -d` antes de ejecutar las verificaciones.

```bash
# ── 1. Estado general ─────────────────────────────────────────────
cd ~/podman/ticket-classification
podman ps
# Todos los contenedores deben aparecer con STATUS "Up"

# ── 2. Health checks ──────────────────────────────────────────────
curl -s http://localhost:8001/health | python3 -m json.tool
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:11434/api/tags | python3 -m json.tool

# ── 3. Prueba: ticket de IT ───────────────────────────────────────
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "texto": "El servidor de producción no responde desde las 9am. Usuarios sin acceso.",
    "origen": "webhook"
  }' | python3 -m json.tool
# Resultado esperado:
# {
#   "run_id": "...",
#   "dominio": "IT",
#   "categoria": "incidente",
#   "prioridad": "alta",
#   "confianza": 0.95,
#   "iterations_used": 1,
#   "validated": true,
#   "cached": false
# }

# ── 4. Prueba: ticket de cliente ──────────────────────────────────
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "texto": "Mi factura del mes pasado tiene un cargo duplicado de $500",
    "origen": "webhook"
  }' | python3 -m json.tool

# ── 5. Prueba: ticket de operaciones ──────────────────────────────
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "texto": "El proceso de cierre contable no terminó. Hay errores en el batch.",
    "origen": "webhook"
  }' | python3 -m json.tool

# ── 6. Verificar persistencia en PostgreSQL ───────────────────────
podman exec -it postgres psql -U admin -d ai \
  -c "SELECT id, dominio, categoria, prioridad, confianza, origen FROM ss_tickets ORDER BY fecha DESC LIMIT 5;"

# ── 7. Verificar cache Redis (segunda llamada debe mostrar cached: true)
# Enviar el mismo ticket dos veces y comparar tiempos de respuesta
# Primera vez: ~15-40s (Ollama infiere)
# Segunda vez: <100ms (Redis cache)

# ── 8. Accesos web (abrir en navegador de Windows) ────────────────
# Grafana        → http://localhost:3000       (admin / admin)
# Swagger agente → http://localhost:8001/docs
# Swagger API    → http://localhost:8000/docs
# Prometheus     → http://localhost:9090
# LangSmith      → https://smith.langchain.com
```

---

## 12. Comandos de uso diario

> ⚠️ **Regla de oro:** Siempre ejecutar desde `~/podman/ticket-classification`

```bash
# ── Acceso rápido a la raíz ───────────────────────────────────────
cd ~/podman/ticket-classification

# ── Ciclo de vida del stack ───────────────────────────────────────
podman-compose up -d                          # Levantar todo
podman-compose down                           # Apagar todo (datos se conservan)
podman-compose restart langchain-agent        # Reiniciar un servicio
podman ps                                     # Estado de contenedores
podman stats --no-stream                      # Uso de CPU y RAM

# ── Logs ──────────────────────────────────────────────────────────
podman-compose logs -f                        # Todos los servicios en tiempo real
podman logs -f langchain-agent                # Solo el agente
podman logs -f langchain-api                  # Solo la API
podman logs --tail 100 langchain-agent        # Últimas 100 líneas

# ── Desarrollo: reconstruir después de cambios ────────────────────
cd ~/podman/ticket-classification
podman-compose build langchain-agent          # Reconstruir imagen del agente
podman-compose up -d langchain-agent          # Reemplazar el contenedor

cd ~/podman/ticket-classification
podman-compose build langchain-api            # Reconstruir imagen de la API
podman-compose up -d langchain-api

cd ~/podman/ticket-classification                          # Reconstruir todo desde cero
podman-compose down
podman-compose build --no-cache
podman-compose up -d

# ── Base de datos ─────────────────────────────────────────────────
podman exec -it postgres psql -U admin -d ai  # Conectarse a PostgreSQL

# Ver últimos tickets clasificados
podman exec -it postgres psql -U admin -d ai \
  -c "SELECT id, dominio, categoria, prioridad, confianza, origen, fecha \
      FROM ss_tickets ORDER BY fecha DESC LIMIT 10;"

# Ver ejecuciones del agente
podman exec -it postgres psql -U admin -d ai \
  -c "SELECT run_id, iterations_used, validated, provider_usado, duracion_ms \
      FROM ss_agent_runs ORDER BY fecha DESC LIMIT 10;"

# ── Cambiar provider sin reiniciar el stack ───────────────────────
# Solo pasar el provider en el body del request
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"texto": "Tu ticket aquí", "origen": "webhook", "provider": "openai"}'
# Providers: ollama | openai | anthropic | gemini

# ── Ollama ────────────────────────────────────────────────────────
podman exec -it ollama ollama list            # Ver modelos descargados
podman exec -it ollama ollama pull llama3.2:3b # Descargar/actualizar modelo

# ── Git ───────────────────────────────────────────────────────────
cd ~/podman/ticket-classification
git status
git add .
git commit -m "feat: descripción del cambio"
git push origin main
```

---

## 13. Troubleshooting inicial

### Contenedor no arranca

```bash
cd ~/podman/ticket-classification
podman logs langchain-agent        # Ver error específico
podman events --since 10m          # Ver eventos recientes de Podman
```

### "Cannot connect to Podman socket"

```bash
# Reiniciar el socket
systemctl --user restart podman.socket
systemctl --user status podman.socket

# Restaurar variable de entorno si se perdió
export DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock
echo $DOCKER_HOST   # Verificar
```

### Ollama responde muy lento (>60s)

```bash
# Normal en CPU sin GPU — verificar RAM disponible
free -h
# Si RAM libre < 4 GB, cerrar aplicaciones en Windows

# Verificar modelo descargado correctamente
podman exec -it ollama ollama list
```

### Error de comunicación entre contenedores

```bash
# INCORRECTO — nunca usar localhost dentro de contenedores:
#   http://localhost:8000/ask
#   localhost:5432

# CORRECTO — usar el nombre del servicio de docker-compose.yml:
#   http://langchain-api:8000/ask
#   postgres:5432
#   redis:6379
#   ollama:11434
```

### Puerto ya en uso

```bash
# Ver qué proceso usa el puerto (ejemplo: 8001)
ss -tlnp | grep 8001

# Si es un contenedor previo sin apagar:
cd ~/podman/ticket-classification
podman-compose down
podman-compose up -d
```

### Promtail no envía logs a Loki

```bash
# Verificar ruta exacta de logs en Podman rootless
podman inspect langchain-agent --format '{{.LogPath}}'

# Si la ruta no coincide, actualizar __path__ en promtail.yml
nano ~/podman/ticket-classification/promtail.yml

# Reiniciar Promtail
cd ~/podman/ticket-classification
podman-compose restart promtail
```

### Verificación rápida de todo el sistema

```bash
cd ~/podman/ticket-classification
echo "=== CONTENEDORES ===" \
  && podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo "=== AGENTE ===" \
  && curl -s http://localhost:8001/health
echo "=== API ===" \
  && curl -s http://localhost:8000/health
echo "=== OLLAMA ===" \
  && podman exec -it ollama ollama list
echo "=== POSTGRES ===" \
  && podman exec -it postgres psql -U admin -d ai -c "\dt ss_*"
```

---

## 14. Referencia rápida de puertos

| Servicio | URL | Credenciales | Descripción |
|---|---|---|---|
| LangChain Agent | http://localhost:8001 | sin auth | Clasificador principal |
| Agent Swagger | http://localhost:8001/docs | sin auth | Documentación interactiva del agente |
| LangChain API | http://localhost:8000 | sin auth | Gateway de LLMs |
| API Swagger | http://localhost:8000/docs | sin auth | Documentación interactiva de la API |
| Ollama | http://localhost:11434 | sin auth | Modelos de IA locales |
| PostgreSQL | localhost:5432 | admin / admin / db:ai | Base de datos |
| Redis | localhost:6379 | sin auth | Cache y estado del agente |
| Prometheus | http://localhost:9090 | sin auth | Métricas raw |
| Grafana | http://localhost:3000 | admin / admin | Dashboards |
| Node Exporter | http://localhost:9100 | sin auth | Métricas del host |
| Loki | http://localhost:3100 | sin auth | API de logs |
| LangSmith | https://smith.langchain.com | cuenta Google | Trazas del agente |

---

*shared-services-classifier · Setup WSL + Windows · Marzo 2026*
