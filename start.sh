#!/bin/bash
# =============================================================================
# start.sh — Arranque del stack ticket-classification con IP dinámica de Windows
# Uso: ~/stack_ticket/ticket-classification/start.sh
#
# Necesario cuando ticket-management-backend corre en Windows (Podman Desktop).
# La IP del host Windows cambia entre redes y reinicios de WSL.
# Este script la detecta y actualiza el .env antes de levantar el stack.
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

# Detectar IP del host Windows desde WSL (via ruta default, más confiable que resolv.conf)
WSL_HOST_IP=$(ip route show | grep default | awk '{print $3}')

if [ -z "$WSL_HOST_IP" ]; then
  echo "[ERROR] No se pudo detectar la IP del host Windows"
  exit 1
fi

echo "[start.sh] IP del host Windows: $WSL_HOST_IP"

# Actualizar TICKET_MGMT_API_URL en .env con la IP actual
sed -i "s|^TICKET_MGMT_API_URL=.*|TICKET_MGMT_API_URL=http://$WSL_HOST_IP:8080/api/v1|" "$ENV_FILE"

echo "[start.sh] TICKET_MGMT_API_URL actualizado: http://$WSL_HOST_IP:8080/api/v1"

# Asegurar redes externas requeridas por este stack
if ! podman network ls | grep -q "ticket-management-network"; then
  echo "[start.sh] Creando ticket-management-network..."
  podman network create ticket-management-network
fi

if ! podman network ls | grep -q "ticket-classification-network"; then
  echo "[start.sh] Creando ticket-classification-network..."
  podman network create ticket-classification-network
fi

# Levantar el stack
cd "$STACK_DIR"
podman-compose down 2>/dev/null || true
podman-compose up -d

echo "[start.sh] Stack levantado. Verificando contenedores..."
podman ps --format "table {{.Names}}\t{{.Status}}"
