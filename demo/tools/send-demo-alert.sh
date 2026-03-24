#!/bin/sh
set -eu

AIOPS_URL="${AIOPS_URL:-http://localhost:8000/genai/alerts/ingest/}"
ALERT_NAME="${1:-DemoAppLatencyHigh}"
TARGET_HOST="${2:-gateway}"
SERVICE_NAME="${3:-app-orders}"

curl -fsS -X POST "${AIOPS_URL}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"alert_name\": \"${ALERT_NAME}\",
    \"target_host\": \"${TARGET_HOST}\",
    \"labels\": {
      \"alertname\": \"${ALERT_NAME}\",
      \"service\": \"${SERVICE_NAME}\",
      \"instance\": \"${SERVICE_NAME}:8000\"
    },
    \"annotations\": {
      \"summary\": \"${ALERT_NAME} fired for ${SERVICE_NAME}\"
    },
    \"execute\": false
  }"
