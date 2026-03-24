#!/bin/sh
set -eu

SERVICE="${1:-all}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
. "${SCRIPT_DIR}/toxiproxy-common.sh"

ensure_demo_proxies

apply_toxic() {
  proxy_name="$1"
  toxic_name="$2"

  curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/${proxy_name}/toxics/${toxic_name}" >/dev/null 2>&1 || true
  curl -fsS -X POST "${TOXIPROXY_URL}/proxies/${proxy_name}/toxics" \
    -H 'Content-Type: application/json' \
    -d "{
      \"name\": \"${toxic_name}\",
      \"type\": \"timeout\",
      \"stream\": \"downstream\",
      \"attributes\": {
        \"timeout\": 60000
      }
    }" >/dev/null
}

case "$SERVICE" in
  orders)
    apply_toxic orders_demo gateway_orders_down
    ;;
  inventory)
    apply_toxic inventory_demo gateway_inventory_down
    ;;
  billing)
    apply_toxic billing_demo gateway_billing_down
    ;;
  all)
    apply_toxic orders_demo gateway_orders_down
    apply_toxic inventory_demo gateway_inventory_down
    apply_toxic billing_demo gateway_billing_down
    ;;
  *)
    echo "Unsupported service: $SERVICE" >&2
    echo "Use one of: orders, inventory, billing, all" >&2
    exit 1
    ;;
esac

echo "Cut gateway-to-app traffic for ${SERVICE}."
