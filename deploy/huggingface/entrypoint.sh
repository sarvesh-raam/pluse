#!/bin/sh
set -e

cd /app/backend

echo "Running migrations..."
alembic upgrade head

echo "Seeding demo data (idempotent, safe to re-run)..."
python -m app.seed || echo "Seed skipped/failed — continuing anyway."

echo "Starting api + scheduler + worker + nginx..."
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
