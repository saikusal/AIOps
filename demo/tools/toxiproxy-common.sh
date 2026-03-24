#!/bin/sh

TOXIPROXY_URL="${TOXIPROXY_URL:-http://localhost:8474}"

ensure_proxy() {
  proxy_name="$1"
  listen_addr="$2"
  upstream_addr="$3"

  if ! curl -fsS "${TOXIPROXY_URL}/proxies/${proxy_name}" >/dev/null 2>&1; then
    curl -fsS -X POST "${TOXIPROXY_URL}/proxies" \
      -H 'Content-Type: application/json' \
      -d "{
        \"name\": \"${proxy_name}\",
        \"listen\": \"${listen_addr}\",
        \"upstream\": \"${upstream_addr}\"
      }" >/dev/null
  fi
}

ensure_demo_proxies() {
  ensure_proxy postgres_demo "0.0.0.0:15432" "db:5432"
  ensure_proxy orders_demo "0.0.0.0:18001" "app-orders:8000"
  ensure_proxy inventory_demo "0.0.0.0:18002" "app-inventory:8000"
  ensure_proxy billing_demo "0.0.0.0:18003" "app-billing:8000"
}
