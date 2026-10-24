# syntax=docker/dockerfile:1
# One image, three roles: api (default CMD), scheduler and worker (override
# the command). Everything runs as an unprivileged user.

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY app ./app
# runtime deps only — pytest/ruff stay out of the production image
RUN pip install .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    WORKER_HEALTH_FILE=/tmp/pulse-worker-healthy

# curl for the compose healthcheck; asyncpg/psutil ship wheels so no compiler needed
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 pulse

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=pulse:pulse app ./app
COPY --chown=pulse:pulse alembic ./alembic
COPY --chown=pulse:pulse alembic.ini ./

USER 10001
EXPOSE 8000 9100 9101

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
