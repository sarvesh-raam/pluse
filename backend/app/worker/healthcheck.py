"""Liveness probe for the worker: exits 0 if the worker's heartbeat loop has
touched its health file recently, 1 otherwise.

    python -m app.worker.healthcheck

Used by the Kubernetes livenessProbe and the docker-compose healthcheck. A
worker whose event loop is wedged (stuck handler blocking the loop, dead DB
connection pool) stops heartbeating, so the probe fails and the orchestrator
restarts it — the same signal the reaper uses to requeue its jobs.
"""

import sys
import time
from pathlib import Path

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    max_age = max(settings.heartbeat_sec * 3, 15)
    try:
        age = time.time() - Path(settings.worker_health_file).stat().st_mtime
    except FileNotFoundError:
        print("unhealthy: no heartbeat recorded yet")
        return 1
    if age > max_age:
        print(f"unhealthy: last heartbeat {age:.0f}s ago (limit {max_age}s)")
        return 1
    print(f"healthy: last heartbeat {age:.0f}s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
