# Seguridad pendiente — Pre-deploy AWS

📁 **Archivo:** `docs/05_seguridad_pendiente_pre_deploy.md`
📌 **Propósito:** Registrar los problemas de seguridad identificados antes del deploy en AWS, con su ubicación exacta en el código y acciones concretas a implementar.

---

## 🔴 Crítico — bloquean el deploy

### 1. Sin autenticación en endpoints propios

**Dónde:** `langchain-agent/main.py` líneas 234–272
```python
@app.post("/process", ...)       # sin validación de API key
@app.get("/status/{job_id}", ...) # sin validación de API key
```
**Acción:** Agregar validación de `X-Api-Key` en header, usando el mismo patrón que ya existe para llamar a ticket-management-backend. Definir la key en `.env` como `AGENT_API_KEY`.

---

### 2. Credenciales por defecto hardcodeadas

**Dónde:** `langchain-agent/agent.py` líneas 97–100
```python
SS_TICKET_API_KEY = os.getenv("SS_TICKET_API_KEY", "change-this-secret-key-in-production")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin")   # via DATABASE_URL
MINIO_SECRET_KEY  = os.getenv("MINIO_SECRET_KEY", "minioadmin123")  # en docker-compose.yml
```
**Acción:** Eliminar todos los defaults inseguros. En AWS usar **Secrets Manager** o **Parameter Store**. Las variables deben fallar explícitamente si no están definidas, no caer en un default débil.

---

### 3. Puertos internos expuestos al host

**Dónde:** `docker-compose.yml` — todos los servicios tienen `ports:` hacia el host

| Servicio | Puerto expuesto | Debe ser |
|---|---|---|
| postgres | 5432 | solo red interna |
| redis | 6379 | solo red interna |
| prometheus | 9090 | solo red interna |
| loki | 3100 | solo red interna |
| node-exporter | 9100 | solo red interna |

**Acción:** Eliminar el bloque `ports:` de estos servicios en el `docker-compose.yml` de producción. Solo `langchain-agent` (8001) y `grafana` (3000) deben ser accesibles, y únicamente detrás del ALB.

---

### 4. Redis sin autenticación

**Dónde:** `langchain-agent/main.py` línea 26–28
```python
redis_client = aioredis.from_url("redis://redis:6379", ...)
```
**Acción:** Agregar `requirepass` en la configuración de Redis y actualizar la URL a `redis://:PASSWORD@redis:6379`. Los jobs en Redis contienen asunto, cuerpo del correo y datos del remitente.

---

## 🟡 Importante — riesgo real en producción

### 5. `/health` expone configuración interna

**Dónde:** `langchain-agent/main.py` líneas 223–232
```python
return {
    "agent_provider": ...,
    "agent_domains": ...,
    "max_iterations": ...,
    "validation_enabled": ...,
}
```
**Acción:** Limitar la respuesta a `{"status": "ok"}` en el endpoint público, o proteger el detalle con el mismo `X-Api-Key`.

---

### 6. `/metrics` sin protección

**Dónde:** `langchain-agent/main.py` línea 20
```python
Instrumentator().instrument(app).expose(app)  # expone /metrics sin auth
```
**Acción:** Mover `/metrics` a un puerto interno separado, o protegerlo con middleware. Prometheus debe hacer scrape desde dentro de la red, no desde internet.

---

### 7. Sin rate limiting en `/process`

**Dónde:** `langchain-agent/main.py` línea 234

**Riesgo:** Un atacante puede saturar el agente con peticiones masivas. Si el provider es OpenAI/Anthropic, cada petición tiene costo directo.

**Acción:** Implementar rate limiting con `slowapi` (librería FastAPI) o a nivel de ALB en AWS. Ejemplo: máximo 10 requests/minuto por IP.

---

### 8. Sin validación de tamaño de input

**Dónde:** `langchain-agent/main.py` — modelos `ProcessRequest` y `AdjuntoInfo`
```python
cuerpo: str               # sin límite de tamaño
contenido_b64: Optional[str]  # sin límite de tamaño
```
**Acción:** Agregar validación en Pydantic:
```python
cuerpo: str = Field(..., max_length=50_000)
contenido_b64: Optional[str] = Field(None, max_length=10_000_000)  # ~7.5MB
```

---

### 9. Sin HTTPS

**Acción:** En AWS, colocar un **Application Load Balancer (ALB)** con certificado **ACM** (gratuito) terminando TLS. Los contenedores siguen en HTTP internamente, el ALB hace el bridge HTTPS → HTTP.

---

## 🟢 Menor — buenas prácticas

### 10. Grafana con credenciales por defecto

**Dónde:** `docker-compose.yml`
```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
```
**Acción:** Definir `GRAFANA_PASSWORD` en `.env` con una contraseña fuerte antes del deploy.

---

### 11. Sin CORS configurado

**Dónde:** `langchain-agent/main.py` — FastAPI sin `CORSMiddleware`

**Acción:** Agregar `CORSMiddleware` con `allow_origins` explícito (solo el dominio de Power Automate o el frontend, no `*`).

---

## Orden de implementación sugerido

| # | Tarea | Archivo | Esfuerzo |
|---|---|---|---|
| 1 | API key en `/process` y `/status` | `main.py` | Bajo |
| 2 | Redis con password | `docker-compose.yml` + `main.py` | Bajo |
| 3 | Eliminar `ports:` de servicios internos | `docker-compose.yml` | Bajo |
| 4 | HTTPS vía ALB + ACM | Infraestructura AWS | Medio |
| 5 | Rate limiting con `slowapi` | `main.py` | Bajo |
| 6 | Límite de tamaño en request body | `main.py` | Bajo |
| 7 | Proteger `/health` y `/metrics` | `main.py` | Bajo |
| 8 | Eliminar defaults inseguros en variables | `agent.py` + `.env` | Bajo |
| 9 | CORS configurado | `main.py` | Bajo |
| 10 | Password Grafana | `.env` | Mínimo |
