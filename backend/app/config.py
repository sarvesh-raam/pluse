from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Pulse"
    env: str = "development"

    database_url: str = (
        "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"
    )

    jwt_secret: str = "dev-only-please-change-this-secret-before-any-real-deployment"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:7860",
        "https://huggingface.co",
    ]

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=require" in url:
            url = url.replace("sslmode=require", "ssl=require")
        elif "sslmode=" in url:
            import re
            url = re.sub(r"sslmode=[^&]+", "ssl=require", url)
        return url

    heartbeat_sec: int = 5
    visibility_timeout_sec: int = 30
    sched_tick_sec: int = 1
    reaper_tick_sec: int = 5

    worker_project_slug: str = "demo"
    worker_queues: str = ""  # comma-separated queue names; empty = all queues in the project
    worker_concurrency: int = 5
    worker_poll_interval_sec: float = 1.0
    worker_shutdown_grace_sec: float = 30.0

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"


@lru_cache
def get_settings() -> Settings:
    return Settings()
