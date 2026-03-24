#!/bin/sh
set -eu

TOXIPROXY_URL="${TOXIPROXY_URL:-http://toxiproxy:8474}"

until curl -fsS "${TOXIPROXY_URL}/version" >/dev/null 2>&1; do
  sleep 1
done

curl -fsS -X POST "${TOXIPROXY_URL}/proxies" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "postgres_demo",
    "listen": "0.0.0.0:15432",
    "upstream": "db:5432"
  }' >/dev/null 2>&1 || true

curl -fsS -X POST "${TOXIPROXY_URL}/proxies" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "orders_demo",
    "listen": "0.0.0.0:18001",
    "upstream": "app-orders:8000"
  }' >/dev/null 2>&1 || true

curl -fsS -X POST "${TOXIPROXY_URL}/proxies" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "inventory_demo",
    "listen": "0.0.0.0:18002",
    "upstream": "app-inventory:8000"
  }' >/dev/null 2>&1 || true

curl -fsS -X POST "${TOXIPROXY_URL}/proxies" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "billing_demo",
    "listen": "0.0.0.0:18003",
    "upstream": "app-billing:8000"
  }' >/dev/null 2>&1 || true
