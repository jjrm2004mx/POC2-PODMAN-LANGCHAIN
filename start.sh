#!/bin/bash
# =============================================================================
# start.sh — Arranque del stack con IP dinámica de Windows
# Uso: ~/podman/ai-stack/start.sh
#
# Necesario cuando ticket-management-backend corre en Windows (Podman Desktop).
# La IP del host Windows cambia entre redes y reinicios de WSL.
# Este script la detecta y actualiza el .env antes de levantar el stack.
# =============================================================================

set -e

STACK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STACK_DIR/.env"

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

# Levantar el stack forzando recreación para que tome los nuevos env vars
cd "$STACK_DIR"
podman-compose down
podman-compose up -d

echo "[start.sh] Stack levantado. Verificando contenedores..."
podman ps --format "table {{.Names}}\t{{.Status}}"
