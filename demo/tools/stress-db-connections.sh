#!/bin/sh
set -eu

TARGET_URL="${TARGET_URL:-http://localhost:8088/api/orders}"
REQUESTS="${1:-30}"
HOLD_SECONDS="${2:-10}"

i=0
while [ "$i" -lt "$REQUESTS" ]; do
  curl -fsS "${TARGET_URL}?sleep=${HOLD_SECONDS}" >/dev/null 2>&1 &
  i=$((i + 1))
done

wait
