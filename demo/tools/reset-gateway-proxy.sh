#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
. "${SCRIPT_DIR}/toxiproxy-common.sh"

ensure_demo_proxies

curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/orders_demo/toxics/gateway_orders_latency" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/orders_demo/toxics/gateway_orders_down" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/inventory_demo/toxics/gateway_inventory_latency" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/inventory_demo/toxics/gateway_inventory_down" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/billing_demo/toxics/gateway_billing_latency" >/dev/null 2>&1 || true
curl -fsS -X DELETE "${TOXIPROXY_URL}/proxies/billing_demo/toxics/gateway_billing_down" >/dev/null 2>&1 || true

echo "Removed gateway-to-app toxics for all demo services."
