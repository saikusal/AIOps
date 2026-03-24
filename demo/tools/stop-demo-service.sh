#!/bin/sh
set -eu

SERVICE="${1:-}"

if [ -z "$SERVICE" ]; then
  echo "Usage: sh stop-demo-service.sh <db|gateway|app-orders|app-inventory|app-billing>" >&2
  exit 1
fi

docker compose -f /Users/ajithsai.kusal/Desktop/AIOps/docker-compose.yml stop "$SERVICE"

echo "Stopped ${SERVICE}."
