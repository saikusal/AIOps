#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
. "${SCRIPT_DIR}/toxiproxy-common.sh"

ensure_demo_proxies

curl -fsS -X POST "${TOXIPROXY_URL}/proxies/postgres_demo/toxics" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "db_down",
    "type": "timeout",
    "stream": "upstream",
    "attributes": {
      "timeout": 60000
    }
  }'

echo "Injected timeout toxic into postgres_demo."
