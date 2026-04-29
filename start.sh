#!/bin/bash
# =============================================================================
# start.sh — Arranque del stack de clasificación de tickets
# Uso: ~/podman/ticket-classification/start.sh
#
# ticket-management-backend está en la red compartida shared-network,
# por lo que se accede por nombre de contenedor — sin IPs dinámicas.
# =============================================================================

set -e

STACK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STACK_DIR/.env"

echo "[start.sh] TICKET_MGMT_API_URL=http://ticket-management-backend:8080/api/v1"

# Actualizar TICKET_MGMT_API_URL en .env con el nombre de contenedor fijo
sed -i "s|^TICKET_MGMT_API_URL=.*|TICKET_MGMT_API_URL=http://ticket-management-backend:8080/api/v1|" "$ENV_FILE"

# Levantar el stack forzando recreación para que tome los nuevos env vars
cd "$STACK_DIR"
podman-compose down
podman-compose up -d

echo "[start.sh] Stack levantado. Verificando contenedores..."
podman ps --format "table {{.Names}}\t{{.Status}}"
