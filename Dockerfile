# Combined single-container build for Hugging Face Spaces (Docker SDK).
# HF Spaces run exactly one container on one port, unlike the 5-service
# docker-compose.yml used for local dev — this image runs the frontend
# (via nginx), api, scheduler, and worker together under supervisord,
# proxying /api internally instead of talking to separate containers.

FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/alembic.ini

RUN pip install --no-cache-dir -e "./backend[dev]"

COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

COPY deploy/huggingface/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

COPY deploy/huggingface/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY deploy/huggingface/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7860

ENTRYPOINT ["/entrypoint.sh"]
