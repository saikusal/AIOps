#!/bin/sh
set -eu

python /app/agent_server.py &
AGENT_PID=$!

cleanup() {
  kill "$AGENT_PID" >/dev/null 2>&1 || true
}

trap cleanup INT TERM

exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 8 app:app
