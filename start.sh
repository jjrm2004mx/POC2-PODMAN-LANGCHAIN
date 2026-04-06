#!/bin/bash
# =============================================================================
# start.sh — Arranque del stack con IP dinámica de Windows
# Uso: ~/podman/ai-stack/start.sh
#
# Necesario cuando SS-TICKET-SYSTEM corre en Windows (Podman Desktop).
# La IP del host Windows cambia entre redes y reinicios de WSL.
# Este script la detecta y actualiza el .env antes de levantar el stack.
# =============================================================================

set -e

STACK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STACK_DIR/.env"

# Detectar IP del host Windows desde WSL
WSL_HOST_IP=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')

if [ -z "$WSL_HOST_IP" ]; then
  echo "[ERROR] No se pudo detectar la IP del host Windows"
  exit 1
fi

echo "[start.sh] IP del host Windows: $WSL_HOST_IP"

# Actualizar SS_TICKET_API_URL en .env con la IP actual
sed -i "s|SS_TICKET_API_URL=http://[0-9.]*:8080|SS_TICKET_API_URL=http://$WSL_HOST_IP:8080|" "$ENV_FILE"

echo "[start.sh] SS_TICKET_API_URL actualizado: http://$WSL_HOST_IP:8080/api/v1"

# Levantar el stack
cd "$STACK_DIR"
podman-compose up -d

echo "[start.sh] Stack levantado. Verificando contenedores..."
podman ps --format "table {{.Names}}\t{{.Status}}"
