#!/bin/sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:8088}"
MODE="${1:-mixed}"
ITERATIONS="${ITERATIONS:-0}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-2}"
CUSTOMER_NAME="${CUSTOMER_NAME:-Sai Kusal}"
SKU="${SKU:-SKU-100}"
QUANTITY="${QUANTITY:-1}"
AMOUNT="${AMOUNT:-199.00}"

read_traffic() {
  curl -fsS "${BASE_URL}/api/orders" >/dev/null
  curl -fsS "${BASE_URL}/api/inventory" >/dev/null
  curl -fsS "${BASE_URL}/api/billing" >/dev/null
}

write_traffic() {
  order_ref="ord-$(date +%s)-$$-$RANDOM"
  payload=$(printf '{"order_ref":"%s","customer_name":"%s","sku":"%s","quantity":%s,"amount":%s}' \
    "$order_ref" "$CUSTOMER_NAME" "$SKU" "$QUANTITY" "$AMOUNT")

  curl -fsS -X POST "${BASE_URL}/api/orders/create" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null
  curl -fsS -X POST "${BASE_URL}/api/inventory/reserve" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null
  curl -fsS -X POST "${BASE_URL}/api/billing/charge" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null
}

run_once() {
  case "$MODE" in
    read)
      read_traffic
      ;;
    write)
      write_traffic
      ;;
    mixed)
      read_traffic
      write_traffic
      ;;
    *)
      echo "Unsupported mode: $MODE" >&2
      echo "Use one of: read, write, mixed" >&2
      exit 1
      ;;
  esac
}

count=0
echo "Starting demo traffic: mode=${MODE} base_url=${BASE_URL} iterations=${ITERATIONS} sleep=${SLEEP_BETWEEN}s"

while :; do
  count=$((count + 1))
  if run_once; then
    echo "[$count] success"
  else
    echo "[$count] failed" >&2
  fi

  if [ "$ITERATIONS" -gt 0 ] && [ "$count" -ge "$ITERATIONS" ]; then
    break
  fi

  sleep "$SLEEP_BETWEEN"
done

echo "Completed demo traffic after ${count} iteration(s)."
