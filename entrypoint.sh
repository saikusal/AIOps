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
 
# Start the Gunicorn server
echo "Starting Gunicorn server..."
exec gunicorn --workers 2 --bind 0.0.0.0:8000 --timeout 120 aiops_platform.wsgi:application
