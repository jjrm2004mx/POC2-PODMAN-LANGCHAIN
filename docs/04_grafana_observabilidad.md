# 04 — Grafana: Observabilidad del Stack
## shared-services-classifier · Configuración desde cero
**Ruta raíz del proyecto: `~/podman/ai-stack`**
**Marzo 2026**

---

## Índice

1. [Contexto](#1-contexto)
2. [Estructura de provisioning](#2-estructura-de-provisioning)
3. [Archivos de configuración](#3-archivos-de-configuración)
4. [Actualizar docker-compose.yml](#4-actualizar-docker-composeyml)
5. [Permisos Podman rootless](#5-permisos-podman-rootless)
6. [Primer arranque con provisioning](#6-primer-arranque-con-provisioning)
7. [Verificar datasources](#7-verificar-datasources)
8. [Verificar dashboards](#8-verificar-dashboards)
9. [Poblar métricas](#9-poblar-métricas)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Contexto

Grafana se configura mediante **provisioning automático** — archivos YAML y JSON
que Grafana carga al arrancar. Esto permite versionar la configuración en Git
y reproducir el entorno sin configuración manual.

El stack usa:
- **Prometheus** como datasource de métricas
- **Loki** como datasource de logs
- **2 dashboards** preconstruidos para el agente

> ⚠️ **Lección aprendida:** No configurar datasources manualmente en la UI
> si también existe provisioning. Genera duplicados con UIDs diferentes que
> rompen los dashboards. Usar **solo** provisioning.

---

## 2. Estructura de provisioning

Crear la estructura de carpetas desde la raíz del proyecto:

```bash
mkdir -p ~/podman/ai-stack/grafana-provisioning/datasources
mkdir -p ~/podman/ai-stack/grafana-provisioning/dashboards
mkdir -p ~/podman/ai-stack/grafana-provisioning/dashboard-files

# Verificar
tree ~/podman/ai-stack/grafana-provisioning
# Resultado esperado:
# grafana-provisioning
# ├── dashboard-files
# ├── dashboards
# └── datasources
```

---

## 3. Archivos de configuración

### 3.1 Datasources — `datasources/datasources.yml`

```bash
cat > ~/podman/ai-stack/grafana-provisioning/datasources/datasources.yml << 'EOF'
apiVersion: 1

datasources:

  - name: Prometheus
    type: prometheus
    uid: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true

  - name: Loki
    type: loki
    uid: loki
    access: proxy
    url: http://loki:3100
    editable: true
EOF
```

> ⚠️ **Crítico:** El campo `uid` es obligatorio. Sin él, Grafana genera UIDs
> aleatorios en cada reinicio y los dashboards JSON pierden la referencia
> al datasource correcto.

### 3.2 Configuración de dashboards — `dashboards/dashboards.yml`

```bash
cat > ~/podman/ai-stack/grafana-provisioning/dashboards/dashboards.yml << 'EOF'
apiVersion: 1

providers:

  - name: shared-services-classifier
    orgId: 1
    folder: "shared-services-classifier"
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboard-files
EOF
```

### 3.3 Dashboard de métricas — `dashboard-files/agent-metrics.json`

Copiar desde el repositorio o descargar desde el chat:

```bash
cp /mnt/c/Users/TU_USUARIO/Downloads/agent-metrics.json \
   ~/podman/ai-stack/grafana-provisioning/dashboard-files/
```

Paneles incluidos:
- Requests por minuto — `/process`
- Latencia p95 — `/process` y `/ask`
- Tasa de éxito vs errores
- CPU host — impacto de inferencia Ollama
- RAM disponible

### 3.4 Dashboard de logs — `dashboard-files/agent-logs.json`

```bash
cp /mnt/c/Users/TU_USUARIO/Downloads/agent-logs.json \
   ~/podman/ai-stack/grafana-provisioning/dashboard-files/
```

Paneles incluidos:
- Logs en tiempo real — `langchain-agent`
- Logs en tiempo real — `langchain-api`
- Errores filtrados — todos los contenedores

### Verificar estructura completa

```bash
tree ~/podman/ai-stack/grafana-provisioning
# Resultado esperado:
# grafana-provisioning
# ├── dashboard-files
# │   ├── agent-logs.json
# │   └── agent-metrics.json
# ├── dashboards
# │   └── dashboards.yml
# └── datasources
#     └── datasources.yml
# 4 directories, 4 files
```

---

## 4. Actualizar docker-compose.yml

Agregar los volúmenes de provisioning al servicio `grafana`:

```yaml
  grafana:
    image: docker.io/grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    volumes:
      - ./grafana_data:/var/lib/grafana
      - ./grafana-provisioning/datasources:/etc/grafana/provisioning/datasources:ro
      - ./grafana-provisioning/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./grafana-provisioning/dashboard-files:/etc/grafana/provisioning/dashboard-files:ro
    depends_on:
      - prometheus
      - loki
    networks:
      - ai-network
    restart: unless-stopped
```

> ⚠️ **Indentación YAML:** `depends_on` debe tener exactamente 4 espacios
> al mismo nivel que `volumes`. Verificar antes de guardar con:
> `podman-compose config`

---

## 5. Permisos Podman rootless

Grafana corre como UID `472` dentro del contenedor. En Podman rootless
este UID necesita permisos explícitos sobre `grafana_data/`:

```bash
cd ~/podman/ai-stack
podman unshare chown -R 472:472 grafana_data/

# Verificar
ls -la grafana_data/
```

Este paso solo es necesario la primera vez o si el directorio se recreó.

---

## 6. Primer arranque con provisioning

```bash
cd ~/podman/ai-stack

# Si Grafana ya estaba corriendo — bajar todo y subir limpio
podman-compose down
podman-compose up -d

# Verificar que Grafana arrancó
podman ps --format "table {{.Names}}\t{{.Status}}" | grep grafana
# Resultado esperado: grafana   Up X seconds
```

> ⚠️ **No usar** `podman-compose up -d grafana` si otros contenedores
> (prometheus, loki) ya están corriendo — Podman rootless bloquea el
> reemplazo de contenedores con dependientes activos.
> Siempre usar `podman-compose down && podman-compose up -d`.

---

## 7. Verificar datasources

Abrir http://localhost:3000 (admin / admin o tu `GRAFANA_PASSWORD`).

Ir a **Connections → Data sources**.

Deben aparecer exactamente **2 datasources**:

| Nombre | URL en el navegador |
|---|---|
| Prometheus | `.../datasources/edit/prometheus` |
| Loki | `.../datasources/edit/loki` |

Si el UID en la URL no es `prometheus` o `loki` exactamente →
ver sección [Troubleshooting](#10-troubleshooting).

Hacer clic en cada datasource → **Save & test** → debe aparecer ✅.

---

## 8. Verificar dashboards

Ir a **Dashboards** en el menú izquierdo.

Debe aparecer la carpeta **shared-services-classifier** con:
- `shared-services-classifier — Agente`
- `shared-services-classifier — Logs`

Si no aparecen, esperar 30s (Grafana escanea cada `updateIntervalSeconds: 30`)
y recargar la página.

---

## 9. Poblar métricas

Enviar tickets de prueba para que los dashboards muestren datos:

```bash
for texto in \
  "El servidor de producción cayó." \
  "Mi factura tiene un error de cobro." \
  "El proceso de nómina falló esta madrugada." \
  "No puedo acceder al sistema desde ayer."; do
  curl -s -X POST http://localhost:8001/process \
    -H "Content-Type: application/json" \
    -d "{\"texto\": \"$texto\", \"origen\": \"webhook\"}" \
    | python3 -m json.tool | grep -E "dominio|prioridad|validated|cached"
  echo "---"
done
```

- **Dashboard métricas:** Los paneles de CPU y RAM muestran datos inmediatamente.
  Los paneles de requests/latencia muestran datos ~30s después de los tickets.
- **Dashboard logs:** Muestra actividad de contenedores en tiempo real.

---

## 10. Troubleshooting

### UIDs de datasources incorrectos (dashboards sin datos)

**Síntoma:** Los dashboards muestran "No data" aunque Prometheus y Loki funcionan.

**Causa:** Los datasources fueron creados manualmente en la UI además del
provisioning, generando duplicados con UIDs aleatorios.

**Solución:**

```bash
# Detener Grafana
cd ~/podman/ai-stack && podman stop grafana

# Limpiar base de datos de Grafana (elimina datasources manuales)
# Los dashboards NO se pierden — están en dashboard-files/
podman unshare rm -f ~/podman/ai-stack/grafana_data/grafana.db

# Reiniciar — el provisioning recrea todo con UIDs correctos
podman-compose up -d grafana
```

Verificar en Connections → Data sources que los UIDs ahora son `prometheus` y `loki`.

---

### Grafana no arranca — Permission denied en grafana_data/

```bash
podman logs --tail 10 grafana
# Muestra: GF_PATHS_DATA='/var/lib/grafana' is not writable

# Fix
cd ~/podman/ai-stack
podman unshare chown -R 472:472 grafana_data/
podman-compose up -d grafana
```

---

### Datasources muestran error en "Save & test"

Verificar que Prometheus y Loki están corriendo:

```bash
podman ps --format "table {{.Names}}\t{{.Status}}" | grep -E "prometheus|loki"
```

Verificar conectividad desde dentro de la red:

```bash
podman exec -it grafana wget -qO- http://prometheus:9090/-/ready
podman exec -it grafana wget -qO- http://loki:3100/ready
```

Ambos deben responder `ready`.

---

*shared-services-classifier · Grafana Observabilidad · Marzo 2026*
