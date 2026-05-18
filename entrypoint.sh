#!/bin/sh
 
# Wait for the database to be ready
echo "Waiting for database..."
while ! nc -z ${POSTGRES_HOST:-db} 5432; do
  sleep 1
done
echo "Database is ready."

# Apply database migrations
echo "Applying database migrations..."
python3 manage.py migrate --noinput

# Seed default policy packs (idempotent — safe to run on every start)
echo "Seeding policy packs..."
python3 manage.py seed_policy_packs

# Optionally sync local code-context indexes.
# This is best-effort only: startup must continue even when no repositories
# are registered yet or indexing is not enabled for the environment.
if [ "${AIOPS_CODE_CONTEXT_ENABLED:-false}" = "true" ] && [ "${AIOPS_CODE_CONTEXT_PROVIDER:-internal}" = "internal" ]; then
  echo "Syncing local code-context indexes..."
  if ! python3 manage.py sync_code_context --recent-commits "${AIOPS_CODE_CONTEXT_RECENT_COMMITS:-25}"; then
    echo "Code-context sync skipped or failed; continuing startup."
  fi
fi
 
# Bootstrap the platform super-admin if missing.
# Configure via env: AIOPS_ADMIN_USERNAME, AIOPS_ADMIN_EMAIL, AIOPS_ADMIN_PASSWORD.
# Defaults are dev-only — override in production via .env or Helm values.
AIOPS_ADMIN_USERNAME="${AIOPS_ADMIN_USERNAME:-admin}"
AIOPS_ADMIN_EMAIL="${AIOPS_ADMIN_EMAIL:-admin@example.com}"
AIOPS_ADMIN_PASSWORD="${AIOPS_ADMIN_PASSWORD:-password}"

if [ "${AIOPS_ADMIN_PASSWORD}" = "password" ]; then
  echo "WARNING: AIOPS_ADMIN_PASSWORD is using the insecure dev default. Set it in your environment for non-local deployments."
fi

echo "Bootstrapping platform super-admin '${AIOPS_ADMIN_USERNAME}' (if missing)..."
AIOPS_ADMIN_USERNAME="${AIOPS_ADMIN_USERNAME}" \
AIOPS_ADMIN_EMAIL="${AIOPS_ADMIN_EMAIL}" \
AIOPS_ADMIN_PASSWORD="${AIOPS_ADMIN_PASSWORD}" \
python3 manage.py shell <<'EOF'
import os
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ["AIOPS_ADMIN_USERNAME"]
email = os.environ["AIOPS_ADMIN_EMAIL"]
password = os.environ["AIOPS_ADMIN_PASSWORD"]
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f"Superuser '{username}' created.")
else:
    print(f"Superuser '{username}' already exists.")
EOF
 
if [ "$#" -gt 0 ]; then
  echo "Starting custom process: $*"
  exec "$@"
fi

# Start the ASGI server stack.
echo "Starting ASGI server..."
exec gunicorn \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${AIOPS_WEB_CONCURRENCY:-2}" \
  --bind 0.0.0.0:8000 \
  --timeout "${AIOPS_GUNICORN_TIMEOUT:-120}" \
  --keep-alive "${AIOPS_GUNICORN_KEEPALIVE:-15}" \
  --graceful-timeout "${AIOPS_GUNICORN_GRACEFUL_TIMEOUT:-30}" \
  --max-requests "${AIOPS_GUNICORN_MAX_REQUESTS:-1000}" \
  --max-requests-jitter "${AIOPS_GUNICORN_MAX_REQUESTS_JITTER:-100}" \
  aiops_platform.asgi:application
