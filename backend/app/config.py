import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-please-change-this-secret-before-any-real-deployment"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Pulse"
    env: str = "development"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    jwt_secret: str = DEV_JWT_SECRET
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
    def is_production(self) -> bool:
        return self.env.lower() in ("production", "prod")

    @model_validator(mode="after")
    def _refuse_dev_secret_in_production(self) -> "Settings":
        # A guessable signing key lets anyone mint tokens for any user, so
        # fail fast at boot rather than silently running with it.
        if self.is_production and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("JWT_SECRET must be set to a random value of 32+ chars when ENV=production")
        return self

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't understand libpq's sslmode=...; it takes ssl=...
        url = re.sub(r"sslmode=(require|verify-ca|verify-full|prefer)", "ssl=require", url)
        url = re.sub(r"[?&]sslmode=(disable|allow)", "", url)
        # libpq-only params that asyncpg rejects outright (Neon adds these)
        url = re.sub(r"[?&]channel_binding=[^&]+", "", url)
        if "?" not in url and "&" in url:
            url = url.replace("&", "?", 1)
        return url

    heartbeat_sec: int = 5
    visibility_timeout_sec: int = 30
    sched_tick_sec: int = 1
    reaper_tick_sec: int = 5
    heartbeat_retention_hours: int = 6
    dead_worker_retention_hours: int = 24

    worker_project_slug: str = "demo"
    worker_queues: str = ""  # comma-separated queue names; empty = all queues in the project
    worker_concurrency: int = 5
    worker_poll_interval_sec: float = 1.0
    worker_shutdown_grace_sec: float = 30.0
    # Port for the worker/scheduler's own Prometheus /metrics endpoint
    # (the API serves its metrics on its main port). 0 disables it.
    worker_metrics_port: int = 9100
    scheduler_metrics_port: int = 9101
    # File touched on every successful heartbeat; a liveness probe checks
    # its age (see app/worker/healthcheck.py).
    worker_health_file: str = "/tmp/pulse-worker-healthy"

    # Chaos engineering. "auto" deletes the worker's pod through the
    # Kubernetes API when running in-cluster, otherwise asks the worker to
    # crash itself (exit without draining) so its supervisor restarts it.
    chaos_enabled: bool = True
    chaos_mode: str = "auto"  # auto | kubernetes | signal

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"


@lru_cache
def get_settings() -> Settings:
    return Settings()
