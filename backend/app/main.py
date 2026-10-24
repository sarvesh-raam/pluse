from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, chaos, dlq, jobs, metrics, orgs, projects, queues, retry_policies, workers
from app.config import get_settings
from app.core import observability
from app.core.errors import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db import AsyncSessionLocal
from app.ws.publisher import publisher
from app.ws.router import router as ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    publisher.start()
    yield
    await publisher.stop()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
        # interactive docs are handy locally, but needn't be public in prod
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https://.*\.hf\.space",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    api_v1 = "/api/v1"

    app.include_router(auth.router, prefix=api_v1)
    app.include_router(orgs.router, prefix=api_v1)
    app.include_router(projects.router, prefix=api_v1)
    app.include_router(retry_policies.router, prefix=api_v1)
    app.include_router(queues.router, prefix=api_v1)
    app.include_router(jobs.router, prefix=api_v1)
    app.include_router(dlq.router, prefix=api_v1)
    app.include_router(metrics.router, prefix=api_v1)
    app.include_router(workers.router, prefix=api_v1)
    app.include_router(chaos.router, prefix=api_v1)
    app.include_router(ws_router, prefix=api_v1)

    # Liveness: the process is up and serving. Deliberately no DB check — a
    # database outage must not make Kubernetes restart every API pod in a
    # loop (restarting can't fix the DB, and it sheds healthy connections).
    @app.get("/health", include_in_schema=False)
    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    # Readiness: can this pod actually serve requests? Failing it just pulls
    # the pod out of the Service until the DB is reachable again. Replaces
    # the old public /dbcheck, which echoed raw driver errors (hostnames,
    # usernames, SSL details) to anyone who asked.
    @app.get("/readyz", include_in_schema=False)
    async def readyz(response: Response) -> dict:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
        except Exception:
            response.status_code = 503
            return {"status": "unavailable", "database": "unreachable"}
        return {"status": "ready", "database": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        body, content_type = await observability.render_latest()
        return Response(content=body, media_type=content_type)

    return app


app = create_app()
