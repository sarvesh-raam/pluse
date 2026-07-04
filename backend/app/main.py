from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, dlq, jobs, orgs, projects, queues, retry_policies
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging

settings = get_settings()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
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

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
