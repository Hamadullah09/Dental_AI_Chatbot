#!/usr/bin/env bash
# Pull latest main, rebuild the given docker-compose services, recreate them,
# and health-check the result. Run from anywhere inside the repo.
#
# Usage:
#   scripts/deploy.sh              # rebuilds api + frontend (the default)
#   scripts/deploy.sh api          # rebuild just the API
#   scripts/deploy.sh frontend     # rebuild just the frontend
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.dev.yml"
SERVICES=("$@")
if [ ${#SERVICES[@]} -eq 0 ]; then
  SERVICES=(api frontend)
fi

contains() {
  local needle="$1"; shift
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

echo "==> git pull origin main"
git pull origin main

echo "==> Building: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" build "${SERVICES[@]}"

echo "==> Recreating: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" up -d --force-recreate "${SERVICES[@]}"

echo "==> Waiting for containers to settle..."
sleep 5
docker compose -f "$COMPOSE_FILE" ps

if contains api "${SERVICES[@]}"; then
  port=$(docker compose -f "$COMPOSE_FILE" port api 8000 2>/dev/null | awk -F: '{print $NF}') || true
  if [ -n "${port:-}" ]; then
    echo "==> API health check (localhost:${port}):"
    if curl -fsS "http://localhost:${port}/api/health"; then
      echo
    else
      echo "FAILED - check: docker compose -f $COMPOSE_FILE logs api"
    fi
  fi
fi

if contains frontend "${SERVICES[@]}"; then
  port=$(docker compose -f "$COMPOSE_FILE" port frontend 3000 2>/dev/null | awk -F: '{print $NF}') || true
  if [ -n "${port:-}" ]; then
    echo "==> Frontend check (localhost:${port}):"
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/" || echo "000")
    echo "HTTP $code"
  fi
fi

echo
echo "==> Live URLs:"
echo "    https://api.wtechx.tech/api/health"
echo "    https://demo.wtechx.tech"
