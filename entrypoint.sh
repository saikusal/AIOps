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
 
# Create a superuser if one does not exist
echo "Creating superuser..."
python3 manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'password')
    print('Superuser created.')
else:
    print('Superuser already exists.')
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
