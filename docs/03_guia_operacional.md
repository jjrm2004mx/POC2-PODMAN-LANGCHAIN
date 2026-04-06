# 03 — Guía Operacional
## shared-services-classifier · Operaciones del día a día
**Ruta raíz: `~/podman/ai-stack` · Marzo 2026**

---

## Índice

1. [Regla de oro](#1-regla-de-oro)
2. [Ciclo de vida del stack](#2-ciclo-de-vida-del-stack)
3. [Verificación de salud del sistema](#3-verificación-de-salud-del-sistema)
4. [Probar el clasificador](#4-probar-el-clasificador)
5. [Gestión de logs](#5-gestión-de-logs)
6. [Base de datos — operaciones frecuentes](#6-base-de-datos--operaciones-frecuentes)
7. [Cambiar provider de IA](#7-cambiar-provider-de-ia)
8. [Agregar o modificar dominios](#8-agregar-o-modificar-dominios)
9. [Ciclo de desarrollo — cambios en código](#9-ciclo-de-desarrollo--cambios-en-código)
10. [Gestión de Ollama](#10-gestión-de-ollama)
11. [Redis — cache y estado](#11-redis--cache-y-estado)
12. [Observabilidad — Prometheus y Grafana](#12-observabilidad--prometheus-y-grafana)
13. [LangSmith — trazas del agente](#13-langsmith--trazas-del-agente)
14. [Git — control de versiones](#14-git--control-de-versiones)
15. [Troubleshooting](#15-troubleshooting)
16. [Checklist de verificación diaria](#16-checklist-de-verificación-diaria)

---

## 1. Regla de oro

> **Siempre ejecutar desde la raíz del proyecto:**
> ```bash
> cd ~/podman/ai-stack
> ```
> Antes de cualquier comando `podman-compose`, estar en esta carpeta.
> Los servicios se comunican por nombre (`langchain-api:8000`),
> nunca por `localhost` dentro de los contenedores.

---

## 2. Ciclo de vida del stack

### Primera vez — preparación inicial (solo una vez)

```bash
# 1. Crear la red compartida con SS-TICKET-SYSTEM
podman network create shared-network

# 2. Dar permisos de ejecución al script de arranque
chmod +x ~/podman/ai-stack/start.sh
```

### Levantar todo

> **Si SS-TICKET-SYSTEM corre en Windows (Podman Desktop):**
> Usar `start.sh` en lugar de `podman-compose up -d`.
> El script detecta automáticamente la IP del host Windows y actualiza
> el `.env` antes de levantar — funciona igual en casa y en la oficina.

```bash
# Arranque recomendado (detecta IP de Windows automáticamente)
~/podman/ai-stack/start.sh
```

```bash
# Arranque directo (solo si SS-TICKET no está en Windows o la IP es fija)
cd ~/podman/ai-stack
podman-compose up -d
```

```bash
# Verificar que arrancaron todos los contenedores
podman ps
```

### Apagar todo (datos se conservan)

```bash
cd ~/podman/ai-stack
podman-compose down
# Los volúmenes postgres_data/, ollama_data/, grafana_data/ se preservan
```

### Apagar y eliminar volúmenes (reset completo — PRECAUCIÓN)

```bash
cd ~/podman/ai-stack
# ⚠️ Esto borra todos los datos de PostgreSQL, Redis y Grafana
podman-compose down -v
```

### Reiniciar un servicio específico

```bash
cd ~/podman/ai-stack
podman-compose restart langchain-agent   # Reiniciar solo el agente
podman-compose restart langchain-api     # Reiniciar solo la API
podman-compose restart postgres          # Reiniciar solo la BD
```

### Ver estado de todos los contenedores

```bash
podman ps
# Con formato detallado
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Ver uso de recursos

```bash
# Snapshot de CPU y RAM por contenedor
podman stats --no-stream

# Monitoreo continuo (Ctrl+C para salir)
podman stats
```

---

## 3. Verificación de salud del sistema

### Verificación rápida completa

```bash
cd ~/podman/ai-stack

echo "════════════════════════════════════"
echo "ESTADO DEL SISTEMA — $(date)"
echo "════════════════════════════════════"

echo -e "\n── Contenedores ──"
podman ps --format "table {{.Names}}\t{{.Status}}"

echo -e "\n── Agente ──"
curl -s http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo "❌ No responde"

echo -e "\n── API ──"
curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "❌ No responde"

echo -e "\n── Ollama modelos ──"
podman exec ollama ollama list 2>/dev/null || echo "❌ Ollama no disponible"

echo -e "\n── PostgreSQL tablas ──"
podman exec postgres psql -U admin -d ai -c "\dt ss_*" 2>/dev/null || echo "❌ PostgreSQL no disponible"

echo -e "\n── Redis ping ──"
podman exec redis redis-cli ping 2>/dev/null || echo "❌ Redis no disponible"
```

### Verificar acceso a interfaces web

Abrir en el navegador de Windows:

| Interfaz | URL | Credenciales |
|---|---|---|
| Swagger del agente | http://localhost:8001/docs | — |
| Swagger de la API | http://localhost:8000/docs | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| LangSmith | https://smith.langchain.com | cuenta Google |

---

## 4. Probar el clasificador

> **Flujo asíncrono — dos pasos obligatorios:**
> 1. `POST /process` → devuelve un `job_id` inmediatamente (HTTP 202)
> 2. `GET /status/{job_id}` → consultar el resultado (esperar ~20-30s con Ollama)

### Campos del request

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| `asunto` | Sí | Asunto del correo |
| `cuerpo` | Sí | Cuerpo del correo |
| `remitente` | No | Email del remitente (Power Automate lo envía siempre) |
| `conversation_id` | No | ID del hilo Outlook — evita clasificar el mismo hilo dos veces |
| `adjuntos` | No | Lista de `{nombre, tipo}` con metadatos de archivos adjuntos |
| `provider` | No | Override del LLM: `ollama` \| `openai` \| `anthropic` \| `gemini` |
| `max_iterations` | No | Override del máximo de reintentos del agente |

### Ticket de IT (incidente de servidor)

```bash
# Paso 1 — enviar
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Servidor de producción no responde",
    "cuerpo": "El servidor de producción no responde desde las 9am. Los usuarios no pueden acceder al ERP.",
    "remitente": "soporte@empresa.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0001"
  }'
# Respuesta: {"job_id": "abc-123-...", "status": "en_proceso"}

# Paso 2 — consultar resultado (reemplazar el job_id)
curl -s http://localhost:8001/status/PEGA-AQUI-EL-JOB-ID | python3 -m json.tool
```

### Ticket de cliente (factura)

```bash
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Cargo duplicado en factura de marzo",
    "cuerpo": "Mi factura del mes pasado tiene un cargo duplicado de $500. Por favor revisar.",
    "remitente": "cliente@externo.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0002"
  }'
```

### Ticket de operaciones (batch)

```bash
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Error en cierre contable mensual",
    "cuerpo": "El proceso de cierre contable mensual no terminó. Hay errores en el batch de las 2am.",
    "remitente": "contabilidad@empresa.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0003"
  }'
```

### Con adjuntos (flujo completo Power Automate)

```bash
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Error en sistema de nómina",
    "cuerpo": "Desde esta mañana el sistema no permite procesar pagos.",
    "remitente": "juan.perez@empresa.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0004",
    "adjuntos": [
      {"nombre": "captura_error.png", "tipo": "image/png"},
      {"nombre": "reporte.xlsx", "tipo": "application/vnd.ms-excel"}
    ]
  }'
```

### Probar con provider diferente

```bash
# Usando OpenAI en lugar de Ollama (requiere OPENAI_API_KEY en .env)
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Sistema de reportes sin actualizar",
    "cuerpo": "El sistema de reportes de BI lleva 2 horas sin actualizar.",
    "remitente": "operaciones@empresa.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0005",
    "provider": "openai"
  }'
```

### Script end-to-end completo

```bash
# 1. Enviar y capturar job_id
JOB_ID=$(curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Solicitud vacaciones agosto",
    "cuerpo": "Solicito 5 días de vacaciones del 1 al 5 de agosto.",
    "remitente": "rrhh@empresa.com",
    "conversation_id": "AAMkAGI2TI5OGEtZWMxIT0006"
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

echo "Job ID: $JOB_ID"

# 2. Esperar procesamiento y consultar resultado
sleep 25
curl -s http://localhost:8001/status/$JOB_ID | python3 -m json.tool
```

Respuesta esperada cuando está listo:
```json
{
    "status": "completado",
    "dominio": "operaciones",
    "categoria": "vacaciones",
    "prioridad": "baja",
    "confianza": 0.92,
    "ticket_id": 1,
    "validated": true,
    "cached": false
}
```

Estados posibles del `status`:
- `en_proceso` — el agente aún está trabajando, reintentar en unos segundos
- `completado` — clasificación exitosa
- `error` — ver campo `error` con el detalle
- `ignorado` — correo duplicado detectado por `conversation_id`

### Verificar cache Redis (segunda llamada idéntica)

```bash
# Primera llamada — clasifica con Ollama (~25s)
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"asunto": "Test cache", "cuerpo": "Texto de prueba para verificar cache Redis"}'

# Segunda llamada con el mismo asunto+cuerpo — responde desde cache
# En el resultado final: "cached": true
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"asunto": "Test cache", "cuerpo": "Texto de prueba para verificar cache Redis"}'
```

---

## 5. Gestión de logs

### Logs en tiempo real

```bash
cd ~/podman/ai-stack

# Todos los servicios simultáneamente (Ctrl+C para salir)
podman-compose logs -f

# Solo el agente (el más importante)
podman logs -f langchain-agent

# Solo la API
podman logs -f langchain-api

# Ollama (para ver las inferencias)
podman logs -f ollama
```

### Logs históricos

```bash
# Últimas 100 líneas del agente
podman logs --tail 100 langchain-agent

# Logs desde hace 1 hora
podman logs --since 1h langchain-agent

# Logs con timestamps
podman logs -t langchain-agent | tail -50
```

### Buscar en logs

```bash
# Buscar clasificaciones exitosas
podman logs langchain-agent | grep "validated=true"

# Buscar errores
podman logs langchain-agent | grep -i "error"

# Buscar fallos de validación
podman logs langchain-agent | grep "validation_failed"

# Ver iteraciones (cuando el agente reintentó)
podman logs langchain-agent | grep "iteration"
```

### Logs en Grafana (Loki)

Abrir http://localhost:3000 → Explore → seleccionar fuente Loki:

```logql
# Todos los logs del agente
{container="langchain-agent"}

# Clasificaciones exitosas
{container="langchain-agent"} |= "validated=true"

# Errores de validación Pydantic
{container="langchain-agent"} |= "validation_failed"

# Errores en cualquier servicio
{job="containers"} |= "ERROR"

# Logs de un contenedor en un rango de tiempo
{container="langchain-agent"} | json | level="error"
```

---

## 6. Base de datos — operaciones frecuentes

### Conectarse a PostgreSQL

```bash
podman exec -it postgres psql -U admin -d ai
# Para salir: \q
```

### Entender los IDs

| ID | Origen | Tabla / campo |
|----|--------|---------------|
| `job_id` | Generado por el agente en cada POST `/process` | `ss_agent_runs.run_id` |
| `ticket_id` | Generado por Postgres (SERIAL) | `ss_tickets.id` |
| `conversation_id` | Viene de Outlook vía Power Automate | `ss_tickets.conversation_id` |
| `external_ticket_id` | UUID devuelto por SS-TICKET-SYSTEM | `ss_tickets.external_ticket_id` |

### Consultas de operación

```bash
# Ver últimos 10 tickets clasificados
podman exec -it postgres psql -U admin -d ai -c "
SELECT id, asunto, dominio, categoria, prioridad, confianza, remitente, created_at
FROM ss_tickets
ORDER BY created_at DESC
LIMIT 10;"

# Buscar un ticket por job_id (el que devuelve POST /process)
podman exec -it postgres psql -U admin -d ai -c "
SELECT t.id AS ticket_id, t.asunto, t.dominio, t.categoria, t.prioridad,
       r.run_id AS job_id, r.iterations_used, r.validated, r.duracion_ms
FROM ss_tickets t
JOIN ss_agent_runs r ON r.ticket_id = t.id
WHERE r.run_id = 'PEGA-AQUI-EL-JOB-ID';"

# Vista completa: tickets con su ejecución de agente
podman exec -it postgres psql -U admin -d ai -c "
SELECT t.id AS ticket_id, t.asunto, t.dominio, t.categoria, t.prioridad,
       t.confianza, t.requiere_revision, t.conversation_id,
       r.run_id AS job_id, r.iterations_used, r.validated, r.duracion_ms
FROM ss_tickets t
JOIN ss_agent_runs r ON r.ticket_id = t.id
ORDER BY t.id DESC
LIMIT 10;"

# Tickets que requieren revisión manual
podman exec -it postgres psql -U admin -d ai -c "
SELECT id, asunto, dominio, categoria, categoria_propuesta, prioridad, created_at
FROM ss_tickets
WHERE requiere_revision = true
ORDER BY created_at DESC;"

# Tickets de alta prioridad del día
podman exec -it postgres psql -U admin -d ai -c "
SELECT id, asunto, dominio, categoria, remitente, created_at
FROM ss_tickets
WHERE prioridad = 'alta'
  AND created_at >= CURRENT_DATE
ORDER BY created_at DESC;"

# Resumen por dominio hoy
podman exec -it postgres psql -U admin -d ai -c "
SELECT dominio, prioridad, COUNT(*) as total
FROM ss_tickets
WHERE created_at >= CURRENT_DATE
GROUP BY dominio, prioridad
ORDER BY dominio, prioridad;"

# Ver ejecuciones recientes del agente (trazabilidad)
podman exec -it postgres psql -U admin -d ai -c "
SELECT run_id AS job_id, ticket_id, iterations_used, validated, provider_usado, duracion_ms
FROM ss_agent_runs
ORDER BY id DESC
LIMIT 10;"

# Performance del agente: distribución de iteraciones
podman exec -it postgres psql -U admin -d ai -c "
SELECT iterations_used, COUNT(*) as total,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as pct
FROM ss_agent_runs
GROUP BY iterations_used
ORDER BY iterations_used;"
```

### Backup rápido de la base de datos

```bash
# Crear backup con fecha
podman exec postgres pg_dump -U admin ai \
  > ~/podman/ai-stack/backup_$(date +%Y%m%d_%H%M%S).sql

# Verificar backup
ls -lh ~/podman/ai-stack/backup_*.sql
```

### Restaurar backup

```bash
# Restaurar desde un backup específico
podman exec -i postgres psql -U admin -d ai \
  < ~/podman/ai-stack/backup_20260315_143022.sql
```

---

## 7. Cambiar provider de IA

### Por request (sin reiniciar nada — recomendado para pruebas)

```bash
# Pasar el provider en el body del request
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Asunto del correo",
    "cuerpo": "Cuerpo del correo aquí",
    "remitente": "usuario@empresa.com",
    "provider": "openai"
  }'
# Providers: ollama | openai | anthropic | gemini
```

### Por defecto permanente (cambiar .env + reiniciar agente)

```bash
cd ~/podman/ai-stack

# 1. Editar .env
nano ~/podman/ai-stack/.env
# Cambiar: AGENT_PROVIDER=openai

# 2. Reiniciar solo el agente (no todo el stack)
podman-compose restart langchain-agent

# 3. Verificar el cambio
curl -s http://localhost:8001/health | python3 -m json.tool
```

### Verificar que las keys de los providers cloud están activas

```bash
# Probar OpenAI directamente
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Di hola", "provider": "openai"}' \
  | python3 -m json.tool

# Probar Anthropic
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Di hola", "provider": "anthropic"}' \
  | python3 -m json.tool
```

---

## 8. Agregar o modificar dominios

Los dominios del clasificador son completamente configurables sin tocar código.

### Agregar un nuevo dominio (ejemplo: RRHH)

```bash
cd ~/podman/ai-stack

# 1. Editar .env
nano ~/podman/ai-stack/.env
# Cambiar: AGENT_DOMAINS=IT,cliente,operaciones,RRHH,otro

# 2. Reiniciar solo el agente
podman-compose restart langchain-agent

# 3. Probar con un ticket del nuevo dominio
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "asunto": "Solicitud de vacaciones",
    "cuerpo": "Necesito solicitar 5 días de vacaciones para la siguiente quincena.",
    "remitente": "empleado@empresa.com"
  }'
# Consultar el job_id devuelto en GET /status/{job_id}
# El agente debe clasificar como dominio=RRHH
```

### Ver dominios activos

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
# El health check muestra los dominios configurados actualmente
```

---

## 9. Ciclo de desarrollo — cambios en código

### Flujo estándar para cambios en el agente

```bash
cd ~/podman/ai-stack

# 1. Editar el código
nano ~/podman/ai-stack/langchain-agent/agent.py

# 2. Reconstruir solo la imagen del agente
podman-compose build langchain-agent

# 3. Reemplazar el contenedor con la nueva imagen
podman-compose up -d langchain-agent

# 4. Ver logs para confirmar que arrancó bien
podman logs -f langchain-agent
# Buscar: "Uvicorn running on http://0.0.0.0:8001"

# 5. Probar el cambio
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"asunto": "Prueba del cambio", "cuerpo": "Verificación tras rebuild del contenedor."}'
```

### Flujo para cambios en la API (langchain-api)

```bash
cd ~/podman/ai-stack

nano ~/podman/ai-stack/langchain-api/main.py
podman-compose build langchain-api
podman-compose up -d langchain-api
podman logs -f langchain-api
```

### Reconstrucción completa desde cero

```bash
cd ~/podman/ai-stack

# Apagar todo
podman-compose down

# Reconstruir todas las imágenes sin cache
podman-compose build --no-cache

# Levantar todo
podman-compose up -d

# Verificar
podman ps
```

### Limpiar imágenes antiguas

```bash
# Ver imágenes sin usar
podman images

# Eliminar imágenes huérfanas
podman image prune -f
```

---

## 10. Gestión de Ollama

### Ver modelos instalados

```bash
podman exec -it ollama ollama list
```

### Descargar un modelo nuevo

```bash
# Modelo ligero (recomendado para clasificación)
podman exec -it ollama ollama pull llama3.2:3b

# Modelo más capaz (requiere más RAM y es más lento)
podman exec -it ollama ollama pull llama3.1:8b

# Verificar descarga
podman exec -it ollama ollama list
```

### Probar un modelo directamente

```bash
podman exec -it ollama ollama run llama3.2:3b "Clasifica este ticket: servidor caído en producción"
# Ctrl+D para salir
```

### Eliminar un modelo (liberar espacio)

```bash
podman exec -it ollama ollama rm llama3.1:8b
```

### Ver uso de recursos de Ollama durante inferencia

```bash
# Mientras Ollama procesa un request, monitorear:
podman stats ollama --no-stream
# RAM usage subirá a ~3GB durante la inferencia
```

---

## 11. Redis — cache y estado

### Verificar que Redis está funcionando

```bash
podman exec -it redis redis-cli ping
# Respuesta esperada: PONG
```

### Ver estadísticas del cache

```bash
# Info general de Redis
podman exec -it redis redis-cli info memory

# Número de keys en cache
podman exec -it redis redis-cli dbsize

# Ver todas las keys (cuidado en producción con muchas keys)
podman exec -it redis redis-cli keys "*"
```

### Limpiar el cache (forzar re-clasificación)

```bash
# Limpiar SOLO el cache de LLM (todas las keys)
podman exec -it redis redis-cli flushdb

# Verificar que se limpió
podman exec -it redis redis-cli dbsize
# Debe mostrar: 0
```

### Inspeccionar una key específica

```bash
# Ver una key específica (los nombres son hashes MD5)
podman exec -it redis redis-cli get "el_hash_md5_aqui"

# Ver TTL restante de una key
podman exec -it redis redis-cli ttl "el_hash_md5_aqui"
# Resultado en segundos (máximo 3600 = 1 hora)
```

### Ver jobs del agente (en_proceso, completado, error)

Los jobs se almacenan en Redis con el prefijo `job:` y TTL de 24h.
La BD solo se escribe cuando el job llega a `completado` — los jobs intermedios solo existen aquí.

```bash
# Listar todos los job_ids activos
podman exec -it redis redis-cli keys "job:*"

# Ver estado de un job específico (el job_id que devolvió POST /process)
podman exec -it redis redis-cli get "job:PEGA-AQUI-EL-JOB-ID"

# Ver todos los jobs con su estado de forma legible
podman exec -it redis redis-cli keys "job:*" | \
  xargs -I{} sh -c 'echo "---"; echo "Key: {}"; podman exec redis redis-cli get "{}"'
```

Ejemplo de respuesta de un job completado:
```json
{
  "status": "completado",
  "asunto": "Error en sistema de nómina",
  "dominio": "IT",
  "categoria": "errores sistema",
  "prioridad": "alta",
  "confianza": 0.95,
  "ticket_id": 2,
  "validated": true
}
```

---

## 12. Observabilidad — Prometheus y Grafana

### Verificar que Prometheus scrapeó todos los targets

Abrir http://localhost:9090 → Status → Targets

Todos los targets deben mostrar estado **UP**:
- `langchain-agent:8001`
- `langchain-api:8000`
- `ollama:11434`
- `node-exporter:9100`
- `localhost:9090` (Prometheus mismo)

### Consultas Prometheus útiles

Abrir http://localhost:9090 → Graph:

```promql
# Total de tickets clasificados
agent_runs_total

# Tickets por origen (webhook, gmail)
agent_runs_total{origen="webhook"}
agent_runs_total{origen="gmail"}

# Tasa de éxito del agente (últimos 5 minutos)
rate(agent_runs_total{status="success"}[5m])

# Latencia promedio del endpoint /process
http_request_duration_seconds{endpoint="/process"}

# Uso de CPU del host
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# RAM disponible en el host
node_memory_MemAvailable_bytes / 1024 / 1024 / 1024
```

### Grafana — primeras configuraciones

**Agregar Loki como data source:**

1. http://localhost:3000 → Configuration → Data Sources → Add data source
2. Seleccionar Loki
3. URL: `http://loki:3100`
4. Save & Test

**Importar dashboard de Node Exporter:**

1. Grafana → Dashboards → Import
2. ID: `1860` (Node Exporter Full)
3. Seleccionar fuente Prometheus
4. Import

---

## 13. LangSmith — trazas del agente

### Acceder a las trazas

1. Abrir https://smith.langchain.com
2. Seleccionar el proyecto `shared-services-classifier-dev`
3. Ver las ejecuciones recientes en la sección "Runs"

### Qué buscar en cada traza

| Campo | Qué indica |
|---|---|
| Total duration | Tiempo total de clasificación |
| Nodo classify → latencia | Tiempo de respuesta del LLM |
| Nodo validate → error | Si hubo problemas de formato JSON |
| iterations_used | Cuántos intentos necesitó el agente |
| confianza | Qué tan seguro estaba el LLM de su respuesta |

### Buscar ejecuciones con problemas

En LangSmith → Runs → filtrar por:
- Status: `Error` — ver ejecuciones que fallaron
- `iterations_used > 1` — ver casos donde el agente reintentó

### Cambiar el proyecto de LangSmith (dev → prod)

```bash
cd ~/podman/ai-stack
nano ~/podman/ai-stack/.env
# Cambiar: LANGCHAIN_PROJECT=shared-services-classifier-prod
podman-compose restart langchain-agent
podman-compose restart langchain-api
```

---

## 14. Git — control de versiones

```bash
cd ~/podman/ai-stack

# Ver estado del repositorio
git status

# Ver cambios antes de commitear
git diff

# Guardar cambios
git add .
git commit -m "feat: descripción clara del cambio"

# Subir al repositorio
git push origin main

# Traer cambios del repositorio (si hay colaboradores)
git pull origin main

# Ver historial
git log --oneline -10
```

### Convención de commits

```
feat: nueva funcionalidad (ej: feat: agregar dominio RRHH)
fix: corrección de bug (ej: fix: validación de confianza)
docs: cambio en documentación
chore: cambios de configuración (ej: chore: actualizar .env.txt)
refactor: mejora de código sin cambio funcional
```

---

## 15. Troubleshooting

### El clasificador devuelve error 500

```bash
# Ver el error específico
podman logs --tail 50 langchain-agent | grep -A5 "ERROR"

# Causas comunes:
# 1. langchain-api no está corriendo
podman ps | grep langchain-api

# 2. Ollama no tiene el modelo descargado
podman exec ollama ollama list

# 3. PostgreSQL no está disponible
podman exec postgres psql -U admin -d ai -c "SELECT 1;"
```

### Ollama no responde o tarda demasiado

```bash
# Verificar que Ollama está corriendo
podman ps | grep ollama

# Verificar RAM disponible (Ollama necesita ~3GB)
free -h

# Reiniciar Ollama
cd ~/podman/ai-stack
podman-compose restart ollama
sleep 10

# Descargar el modelo si no está
podman exec ollama ollama list
podman exec -it ollama ollama pull llama3.2:3b
```

### Error: "connection refused" entre contenedores

```bash
# Verificar que el contenedor destino está corriendo
podman ps | grep langchain-api

# Verificar que está usando el nombre del servicio (no localhost)
# INCORRECTO: http://localhost:8000
# CORRECTO:   http://langchain-api:8000

# Ver logs del contenedor que falla
podman logs langchain-agent | grep "connection refused"
```

### PostgreSQL no acepta conexiones

```bash
# Ver logs de PostgreSQL
podman logs postgres | tail -20

# Reiniciar PostgreSQL
cd ~/podman/ai-stack
podman-compose restart postgres
sleep 15

# Verificar conexión
podman exec postgres psql -U admin -d ai -c "SELECT version();"
```

### Redis no responde

```bash
# Verificar estado
podman ps | grep redis

# Reiniciar Redis
cd ~/podman/ai-stack
podman-compose restart redis

# Test de conexión
podman exec redis redis-cli ping
```

### El socket de Podman no funciona (WSL2)

```bash
# Reiniciar el socket
systemctl --user restart podman.socket
systemctl --user status podman.socket

# Restaurar la variable de entorno
export DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock

# Hacerlo permanente (si se perdió del .bashrc)
echo 'export DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock' >> ~/.bashrc
source ~/.bashrc
```

### Promtail no envía logs a Loki

```bash
# Ver dónde guarda Podman los logs
podman inspect langchain-agent --format '{{.LogPath}}'

# Comparar con __path__ en promtail.yml
cat ~/podman/ai-stack/promtail.yml | grep __path__

# Si no coinciden, actualizar promtail.yml y reiniciar
cd ~/podman/ai-stack
nano promtail.yml
podman-compose restart promtail
```

---

## 16. Checklist de verificación diaria

Ejecutar cada mañana antes de comenzar a trabajar:

```bash
cd ~/podman/ai-stack

# ✅ 1. Contenedores corriendo
podman ps --format "table {{.Names}}\t{{.Status}}" | grep -v "Exited"

# ✅ 2. Agente responde
curl -s http://localhost:8001/health | grep -q "ok" && echo "Agente: OK" || echo "Agente: ❌"

# ✅ 3. API responde
curl -s http://localhost:8000/health | grep -q "ok" && echo "API: OK" || echo "API: ❌"

# ✅ 4. Clasificación funciona (flujo dos pasos)
JOB=$(curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"asunto": "Test diario", "cuerpo": "Verificación de salud del clasificador"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
sleep 25
curl -s http://localhost:8001/status/$JOB \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Clasificador: ' + ('OK - dominio=' + d.get('dominio','?') if d.get('status')=='completado' else '❌ ' + d.get('status','?')))"

# ✅ 5. PostgreSQL accesible
podman exec postgres psql -U admin -d ai -c "SELECT COUNT(*) FROM ss_tickets;" -t \
  && echo "PostgreSQL: OK" || echo "PostgreSQL: ❌"

# ✅ 6. Redis activo
podman exec redis redis-cli ping | grep -q "PONG" && echo "Redis: OK" || echo "Redis: ❌"

# ✅ 7. Disco disponible (>5GB recomendado)
df -h ~/podman/ai-stack

# ✅ 8. RAM disponible (>4GB recomendado para Ollama)
free -h | grep Mem
```

---

## Referencia rápida de comandos

```bash
# ── Stack ────────────────────────────────────────────────────────
~/podman/ai-stack/start.sh                           # Levantar (detecta IP Windows automáticamente)
cd ~/podman/ai-stack && podman-compose down          # Apagar
cd ~/podman/ai-stack && podman-compose restart X     # Reiniciar servicio X
podman ps                                            # Estado
podman stats --no-stream                             # CPU y RAM

# ── Logs ─────────────────────────────────────────────────────────
podman logs -f langchain-agent                       # Agente en tiempo real
podman logs --tail 100 langchain-agent               # Últimas 100 líneas
podman-compose logs -f                               # Todos los servicios

# ── Clasificador ──────────────────────────────────────────────────
# Paso 1 — enviar (devuelve job_id)
curl -s -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{"asunto": "ASUNTO", "cuerpo": "CUERPO", "remitente": "user@empresa.com"}'
# Paso 2 — consultar resultado
curl -s http://localhost:8001/status/JOB_ID | python3 -m json.tool

# ── Base de datos ─────────────────────────────────────────────────
podman exec -it postgres psql -U admin -d ai         # Conectar a PG
# Ver últimos tickets:
podman exec -it postgres psql -U admin -d ai \
  -c "SELECT id, asunto, dominio, categoria, prioridad, created_at FROM ss_tickets ORDER BY id DESC LIMIT 5;"
# Buscar por job_id:
podman exec -it postgres psql -U admin -d ai \
  -c "SELECT t.id, t.asunto, t.dominio, r.run_id AS job_id FROM ss_tickets t JOIN ss_agent_runs r ON r.ticket_id = t.id ORDER BY t.id DESC LIMIT 5;"

# ── Redis ─────────────────────────────────────────────────────────
podman exec redis redis-cli ping                     # Test
podman exec redis redis-cli dbsize                   # Número de keys en cache
podman exec redis redis-cli flushdb                  # Limpiar cache

# ── Ollama ────────────────────────────────────────────────────────
podman exec ollama ollama list                       # Ver modelos
podman exec -it ollama ollama pull llama3.2:3b       # Actualizar modelo

# ── Desarrollo ────────────────────────────────────────────────────
cd ~/podman/ai-stack
podman-compose build langchain-agent && podman-compose up -d langchain-agent

# ── Git ───────────────────────────────────────────────────────────
cd ~/podman/ai-stack && git add . && git commit -m "mensaje" && git push
```

---

*shared-services-classifier · Guía Operacional · Marzo 2026*
