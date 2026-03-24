#!/bin/sh
set -eu

SERVICE="${1:-all}"
LATENCY_MS="${2:-1500}"
JITTER_MS="${3:-200}"

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
      \"type\": \"latency\",
      \"stream\": \"downstream\",
      \"attributes\": {
        \"latency\": ${LATENCY_MS},
        \"jitter\": ${JITTER_MS}
      }
    }" >/dev/null
}

case "$SERVICE" in
  orders)
    apply_toxic orders_demo gateway_orders_latency
    ;;
  inventory)
    apply_toxic inventory_demo gateway_inventory_latency
    ;;
  billing)
    apply_toxic billing_demo gateway_billing_latency
    ;;
  all)
    apply_toxic orders_demo gateway_orders_latency
    apply_toxic inventory_demo gateway_inventory_latency
    apply_toxic billing_demo gateway_billing_latency
    ;;
  *)
    echo "Unsupported service: $SERVICE" >&2
    echo "Use one of: orders, inventory, billing, all" >&2
    exit 1
    ;;
esac

echo "Injected ${LATENCY_MS}ms gateway-to-app latency for ${SERVICE} with ${JITTER_MS}ms jitter."
