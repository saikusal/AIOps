#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
. "${SCRIPT_DIR}/toxiproxy-common.sh"

ensure_demo_proxies

curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/postgres_demo/toxics/db_latency" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/postgres_demo/toxics/db_down" >/dev/null 2>&1 || true

echo "Removed demo toxics from postgres_demo."
