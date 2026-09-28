#!/bin/sh

mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp

cd /app/backend

echo "Running migrations..."
alembic upgrade head || echo "WARNING: Alembic migration failed. Check DATABASE_URL in Space Secrets."

echo "Seeding demo data (idempotent, safe to re-run)..."
python -m app.seed || echo "Seed skipped/failed — continuing anyway."

echo "Starting api + scheduler + worker + nginx..."
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
