"""Prometheus instrumentation shared by every Pulse process.

Each process (api, scheduler, worker) exposes its own /metrics: the API on
its main HTTP port, the scheduler and worker on a dedicated port via
prometheus_client's built-in server. Process-local counters (HTTP traffic,
jobs executed by *this* worker, ...) live in the default registry and are
updated inline. Fleet-wide state (queue depth by status, live workers,
unreplayed DLQ entries) is read from Postgres at scrape time by the API
only, so it's reported exactly once no matter how many workers run.
"""

import asyncio
import logging
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    start_http_server,
)
from sqlalchemy import func, select

logger = logging.getLogger("pulse.metrics")

BUILD_INFO = Info("pulse_build", "Pulse build information")
BUILD_INFO.info({"version": "0.2.0"})

# --- api ---
HTTP_REQUESTS = Counter(
    "pulse_http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "pulse_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
CHAOS_KILLS = Counter("pulse_chaos_kills_total", "Chaos-engineering worker kills issued", ["mode"])

JOBS_BY_STATUS = Gauge("pulse_jobs", "Jobs currently in each status", ["project", "queue", "status"])
QUEUE_PAUSED = Gauge("pulse_queue_paused", "1 if the queue is paused", ["project", "queue"])
WORKERS_BY_STATUS = Gauge("pulse_workers", "Registered workers by status", ["project", "status"])
DLQ_PENDING = Gauge("pulse_dlq_pending", "Dead-letter entries not yet replayed", ["project", "queue"])

# --- worker ---
JOBS_EXECUTED = Counter(
    "pulse_worker_jobs_total", "Job executions finished by this worker", ["handler", "outcome"]
)
JOB_DURATION = Histogram(
    "pulse_worker_job_duration_seconds",
    "Handler execution time",
    ["handler"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 300),
)
WORKER_RUNNING = Gauge("pulse_worker_running_jobs", "Jobs executing on this worker right now")
WORKER_CONCURRENCY = Gauge("pulse_worker_concurrency", "Configured concurrency of this worker")

# --- scheduler / reaper ---
SCHED_PROMOTED = Counter("pulse_scheduler_promoted_total", "Jobs promoted to queued", ["reason"])
SCHED_TICK_SECONDS = Histogram(
    "pulse_scheduler_tick_duration_seconds", "Scheduler tick duration",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
SCHED_LEADER = Gauge("pulse_scheduler_is_leader", "1 if this replica ran the last tick")
REAPER_WORKERS_REAPED = Counter("pulse_reaper_workers_reaped_total", "Workers marked dead")
REAPER_JOBS_RECOVERED = Counter(
    "pulse_reaper_jobs_recovered_total", "Jobs recovered from dead workers", ["outcome"]
)


def observe_http_request(method: str, route: str, status: int, seconds: float) -> None:
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_LATENCY.labels(method, route).observe(seconds)


def start_metrics_server(port: int) -> None:
    if port <= 0:
        return
    try:
        start_http_server(port)
        logger.info("metrics server listening on :%d", port)
    except OSError:
        # Port already taken (e.g. several workers on one host outside a
        # container) — metrics are a nice-to-have, never fatal.
        logger.warning("could not bind metrics port %d — metrics disabled for this process", port)


_FLEET_REFRESH_INTERVAL_SEC = 5.0
_last_fleet_refresh = 0.0
_refresh_lock = asyncio.Lock()


async def _refresh_fleet_gauges() -> None:
    from app.db import AsyncSessionLocal
    from app.models.dead_letter import DeadLetterEntry
    from app.models.job import Job
    from app.models.project import Project
    from app.models.queue import Queue
    from app.models.worker import Worker

    async with AsyncSessionLocal() as db:
        job_rows = (
            await db.execute(
                select(Project.slug, Queue.name, Job.status, func.count())
                .select_from(Job)
                .join(Queue, Queue.id == Job.queue_id)
                .join(Project, Project.id == Queue.project_id)
                .group_by(Project.slug, Queue.name, Job.status)
            )
        ).all()
        queue_rows = (
            await db.execute(
                select(Project.slug, Queue.name, Queue.is_paused).join(
                    Project, Project.id == Queue.project_id
                )
            )
        ).all()
        worker_rows = (
            await db.execute(
                select(Project.slug, Worker.status, func.count())
                .join(Project, Project.id == Worker.project_id)
                .group_by(Project.slug, Worker.status)
            )
        ).all()
        dlq_rows = (
            await db.execute(
                select(Project.slug, Queue.name, func.count())
                .select_from(DeadLetterEntry)
                .join(Queue, Queue.id == DeadLetterEntry.queue_id)
                .join(Project, Project.id == Queue.project_id)
                .where(DeadLetterEntry.replayed_at.is_(None))
                .group_by(Project.slug, Queue.name)
            )
        ).all()

    from app.models.enums import JobStatus, WorkerStatus

    # Rebuild from scratch so deleted queues / emptied statuses drop to 0
    # instead of reporting their last-seen value forever.
    JOBS_BY_STATUS.clear()
    QUEUE_PAUSED.clear()
    WORKERS_BY_STATUS.clear()
    DLQ_PENDING.clear()

    for project, queue, paused in queue_rows:
        QUEUE_PAUSED.labels(project, queue).set(1 if paused else 0)
        for status in JobStatus:
            JOBS_BY_STATUS.labels(project, queue, status.value).set(0)
        DLQ_PENDING.labels(project, queue).set(0)
    for project, queue, status, count in job_rows:
        JOBS_BY_STATUS.labels(project, queue, status.value).set(count)
    for project, queue, count in dlq_rows:
        DLQ_PENDING.labels(project, queue).set(count)
    for project in {row[0] for row in queue_rows} | {row[0] for row in worker_rows}:
        for status in WorkerStatus:
            WORKERS_BY_STATUS.labels(project, status.value).set(0)
    for project, status, count in worker_rows:
        WORKERS_BY_STATUS.labels(project, status.value).set(count)


async def render_latest() -> tuple[bytes, str]:
    """Body + content type for the API's /metrics endpoint. Fleet gauges are
    refreshed at most every few seconds, so an aggressive scrape interval
    (or several Prometheus replicas) can't hammer the database."""
    global _last_fleet_refresh
    async with _refresh_lock:
        if time.monotonic() - _last_fleet_refresh >= _FLEET_REFRESH_INTERVAL_SEC:
            try:
                await _refresh_fleet_gauges()
                _last_fleet_refresh = time.monotonic()
            except Exception:
                logger.exception("failed to refresh fleet gauges")
    return generate_latest(), CONTENT_TYPE_LATEST
