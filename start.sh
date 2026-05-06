#!/bin/bash
# =============================================================================
# start.sh — Arranque del stack ticket-classification
# Uso: ~/stack_ticket/ticket-classification/start.sh
#
# TICKET_MGMT_API_URL se resuelve según el contexto de ejecución:
#   - Normal (via startup.sh): ticket-system-backend corre en la red compartida
#     → usa nombre de contenedor: http://ticket-system-backend:8080/api/v1
#   - Standalone con ticket-management fuera de WSL (Windows/Podman Desktop):
#     → detecta IP del host Windows via ruta default
# =============================================================================

set -e

STACK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STACK_DIR/.env"

# Crear .env desde .env.example si no existe
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$STACK_DIR/.env.example" ]; then
    cp "$STACK_DIR/.env.example" "$ENV_FILE"
    echo "[start.sh] .env creado desde .env.example"
  else
    echo "[ERROR] No se encontro .env ni .env.example en $STACK_DIR"
    exit 1
  fi
fi

# Resolver TICKET_MGMT_API_URL según contexto
if podman ps --format "{{.Names}}" | grep -q "^ticket-system-backend$"; then
  # ticket-system-backend corre como contenedor en la red compartida → usar nombre
  TICKET_MGMT_URL="http://ticket-system-backend:8080/api/v1"
  echo "[start.sh] ticket-system-backend detectado en red compartida"
else
  # Modo standalone: ticket-management fuera de WSL → detectar IP del host Windows
  WSL_HOST_IP=$(ip route show | grep default | awk '{print $3}')
  if [ -z "$WSL_HOST_IP" ]; then
    echo "[ERROR] No se pudo detectar la IP del host — asegurar que ticket-management este corriendo"
    exit 1
  fi
  TICKET_MGMT_URL="http://$WSL_HOST_IP:8080/api/v1"
  echo "[start.sh] Modo standalone — usando IP del host: $WSL_HOST_IP"
fi

sed -i "s|^TICKET_MGMT_API_URL=.*|TICKET_MGMT_API_URL=$TICKET_MGMT_URL|" "$ENV_FILE"
echo "[start.sh] TICKET_MGMT_API_URL=$TICKET_MGMT_URL"

# Asegurar redes externas requeridas por este stack
if ! podman network ls --format "{{.Name}}" | grep -q "^ticket-management-network$"; then
  echo "[start.sh] Creando ticket-management-network..."
  podman network create ticket-management-network
fi

if ! podman network ls --format "{{.Name}}" | grep -q "^ticket-classification-network$"; then
  echo "[start.sh] Creando ticket-classification-network..."
  podman network create ticket-classification-network
fi

# Levantar el stack
cd "$STACK_DIR"
podman-compose down 2>/dev/null || true
podman-compose up -d

echo "[start.sh] Stack levantado. Verificando contenedores..."
podman ps --format "table {{.Names}}\t{{.Status}}"

echo ""
echo "[start.sh] langchain-agent -> http://localhost:8001"
echo "[start.sh] langchain-api   -> http://localhost:8000"
echo "[start.sh] ollama          -> http://localhost:11434"
