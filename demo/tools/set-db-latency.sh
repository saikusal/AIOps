#!/bin/sh
set -eu

LATENCY_MS="${1:-2000}"
JITTER_MS="${2:-250}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
. "${SCRIPT_DIR}/toxiproxy-common.sh"

ensure_demo_proxies

curl -fsS -X POST "${TOXIPROXY_URL}/proxies/postgres_demo/toxics" \
  -H 'Content-Type: application/json' \
  -d "{
    \"name\": \"db_latency\",
    \"type\": \"latency\",
    \"stream\": \"upstream\",
    \"attributes\": {
      \"latency\": ${LATENCY_MS},
      \"jitter\": ${JITTER_MS}
    }
  }"

echo "Injected ${LATENCY_MS}ms latency with ${JITTER_MS}ms jitter into postgres_demo."
