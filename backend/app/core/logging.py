import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core import observability

logger = logging.getLogger("pulse.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            payload.update(extra_fields)
        # logger.exception() attaches exc_info; without this the traceback
        # was silently dropped and every "tick failed" log was undebuggable.
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int | str | None = None) -> None:
    if level is None:
        from app.config import get_settings

        level = get_settings().log_level.upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.user_id = None

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            elapsed = time.perf_counter() - start
            # Label by route template (/jobs/{job_id}), never the raw path —
            # raw paths carry UUIDs and would explode metric cardinality.
            route = request.scope.get("route")
            path_template = getattr(route, "path", None) or "unmatched"
            observability.observe_http_request(request.method, path_template, status_code, elapsed)

        if request.url.path not in ("/health", "/healthz", "/readyz", "/metrics"):
            logger.info(
                "request",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "latency_ms": round(elapsed * 1000, 2),
                        "user_id": request.state.user_id,
                    }
                },
            )
        response.headers["X-Request-ID"] = request_id
        return response
