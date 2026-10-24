import asyncio
import logging
import os
import signal
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import psutil
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core import observability as obs
from app.core.logging import configure_logging
from app.core.notify import CHANNEL as NOTIFY_CHANNEL
from app.core.notify import CHAOS_CHANNEL
from app.db import AsyncSessionLocal
from app.engine import ai_summary, claim, retry
from app.models.enums import ExecutionStatus, JobStatus, LogLevel, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.project import Project
from app.models.queue import Queue
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat
from app.worker.handlers import HANDLERS, JobContext
from app.worker.runtime import WorkerRuntime

logger = logging.getLogger("pulse.worker")

# Exit code of a process killed by SIGKILL (128 + 9) — what a chaos kill
# should look like to the supervisor (docker / kubelet / supervisord).
CHAOS_EXIT_CODE = 137


class WorkerProcess:
    def __init__(self, project_slug: str, queue_names: list[str], concurrency: int):
        self.project_slug = project_slug
        self.queue_names = queue_names  # empty list = subscribe to all queues in the project
        self.runtime = WorkerRuntime(concurrency)
        self.worker_id: uuid.UUID | None = None
        self.project_id: uuid.UUID | None = None
        self.queue_ids: list[uuid.UUID] = []
        self.shutting_down = False
        self._wake_event = asyncio.Event()
        self._notify_conn: asyncpg.Connection | None = None
        self._dsn: str | None = None
        self._process = psutil.Process()
        self._health_file = Path(get_settings().worker_health_file)

    async def _resolve_project(self, db) -> uuid.UUID:
        while True:
            project = await db.scalar(select(Project).where(Project.slug == self.project_slug))
            if project is not None:
                return project.id
            logger.warning(
                "project slug %r not found yet — waiting for seed data", self.project_slug
            )
            await asyncio.sleep(2)

    async def _refresh_queue_ids(self, db) -> list[uuid.UUID]:
        stmt = select(Queue.id).where(Queue.project_id == self.project_id)
        if self.queue_names:
            stmt = stmt.where(Queue.name.in_(self.queue_names))
        return list((await db.scalars(stmt)).all())

    async def register(self) -> None:
        async with AsyncSessionLocal() as db:
            self.project_id = await self._resolve_project(db)
            self.queue_ids = await self._refresh_queue_ids(db)

            hostname = socket.gethostname()  # == pod name under Kubernetes
            worker = Worker(
                project_id=self.project_id,
                name=f"worker-{hostname}-{uuid.uuid4().hex[:6]}",
                hostname=hostname,
                status=WorkerStatus.idle,
                queues=self.queue_names or ["*"],
                concurrency=self.runtime.concurrency,
                last_heartbeat_at=datetime.now(timezone.utc),
            )
            db.add(worker)
            await db.commit()
            await db.refresh(worker)
            self.worker_id = worker.id

        obs.WORKER_CONCURRENCY.set(self.runtime.concurrency)
        obs.WORKER_RUNNING.set_function(lambda: self.runtime.running_count)
        self._touch_health_file()
        logger.info(
            "worker registered",
            extra={"extra_fields": {
                "worker_id": str(self.worker_id),
                "project_id": str(self.project_id),
                "queue_count": len(self.queue_ids),
            }},
        )

    def _touch_health_file(self) -> None:
        try:
            self._health_file.touch()
        except OSError:
            pass

    def _chaos_exit(self, reason: str) -> None:
        """Simulate a hard crash: no draining, no status update, no cleanup.
        In-flight jobs are left claimed/running for the reaper to recover
        once this worker's heartbeat goes stale, and the process supervisor
        (Kubernetes / docker restart policy / supervisord) brings up a
        replacement — which is exactly the self-healing path being shown."""
        logger.warning(
            "chaos: killing worker process",
            extra={"extra_fields": {"worker_id": str(self.worker_id), "reason": reason,
                                     "in_flight": self.runtime.running_count}},
        )
        logging.shutdown()
        os._exit(CHAOS_EXIT_CODE)

    async def heartbeat_loop(self, interval_sec: float) -> None:
        # Prime the CPU counter so the first reading isn't a meaningless 0.0
        self._process.cpu_percent(interval=None)
        while not self.shutting_down:
            await asyncio.sleep(interval_sec)
            try:
                await self._heartbeat_once()
            except Exception:
                logger.exception("heartbeat failed")
            await self._ensure_notify_listener()

    async def _heartbeat_once(self) -> None:
        async with AsyncSessionLocal() as db:
            self.queue_ids = await self._refresh_queue_ids(db)
            now = datetime.now(timezone.utc)
            worker = await db.get(Worker, self.worker_id)
            if worker is None:
                # Row pruned/deleted while we were alive (e.g. a long network
                # partition) — re-register instead of heartbeating into nothing.
                logger.warning("worker row missing — re-registering")
                await self.register()
                return

            if worker.chaos_kill_requested_at is not None:
                self._chaos_exit("kill flag set (heartbeat)")

            # The reaper may have declared us dead during a stall (GC pause,
            # DB blip) and requeued our jobs. We're evidently alive, so come
            # back — otherwise every job we claim from now on would be stolen
            # by the reaper's "jobs under a dead worker" sweep.
            if worker.status == WorkerStatus.dead and not self.shutting_down:
                logger.warning("worker was marked dead but is alive — reviving")
            if not self.shutting_down:
                worker.status = (
                    WorkerStatus.active if self.runtime.running_count else WorkerStatus.idle
                )

            # Per-process figures, not host-wide: several workers on one host
            # would otherwise each report (and the dashboard sum) the whole
            # machine's memory.
            cpu_pct = self._process.cpu_percent(interval=None)
            mem_mb = self._process.memory_info().rss / (1024 * 1024)

            worker.last_heartbeat_at = now
            worker.queues = self.queue_names or ["*"]
            worker.cpu_percent = cpu_pct
            worker.ram_mb = mem_mb
            db.add(
                WorkerHeartbeat(
                    worker_id=self.worker_id,
                    ts=now,
                    running_jobs=self.runtime.running_count,
                    cpu_percent=cpu_pct,
                    ram_mb=mem_mb,
                )
            )
            await db.commit()
        self._touch_health_file()

    async def setup_notify_listener(self, database_url: str) -> None:
        """§10 bonus: event-driven execution. LISTEN on the channel the API/
        scheduler NOTIFY on enqueue/promote/reap, so poll_loop wakes up
        immediately instead of waiting out its normal interval. Polling
        stays as the fallback — if this connection can't be established
        (or drops), the worker still works correctly, just less promptly,
        and heartbeat_loop keeps trying to re-establish it."""
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
        await self._ensure_notify_listener()

    async def _ensure_notify_listener(self) -> None:
        if self._dsn is None or self.shutting_down:
            return
        if self._notify_conn is not None and not self._notify_conn.is_closed():
            return
        try:
            conn = await asyncpg.connect(self._dsn)
            await conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
            await conn.add_listener(CHAOS_CHANNEL, self._on_chaos)
            self._notify_conn = conn
            logger.info("listening for %r notifications", NOTIFY_CHANNEL)
            # anything enqueued while we weren't listening: poll right away
            self._wake_event.set()
        except Exception:
            logger.warning("LISTEN/NOTIFY setup failed — polling only until it reconnects")
            self._notify_conn = None

    def _on_notify(self, _connection, _pid, _channel, _payload) -> None:
        self._wake_event.set()

    def _on_chaos(self, _connection, _pid, _channel, payload: str) -> None:
        if payload == str(self.worker_id):
            self._chaos_exit("kill notification")

    async def close_notify_listener(self) -> None:
        if self._notify_conn is not None and not self._notify_conn.is_closed():
            await self._notify_conn.close()

    async def poll_loop(self, interval_sec: float) -> None:
        while not self.shutting_down:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("poll iteration failed")
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=interval_sec)
            except TimeoutError:
                pass
            self._wake_event.clear()

    async def _poll_once(self) -> None:
        for queue_id in list(self.queue_ids):
            if self.shutting_down:
                return
            free = self.runtime.free_slots
            if free <= 0:
                return
            async with AsyncSessionLocal() as db:
                jobs = await claim.claim_jobs(db, queue_id, self.worker_id, free)
            for job in jobs:
                logger.info(
                    "claimed job",
                    extra={"extra_fields": {
                        "job_id": str(job.id), "queue_id": str(queue_id), "handler": job.handler,
                    }},
                )
                await self.runtime.submit(self._execute(job))

    async def _execute(self, job: Job) -> None:
        attempt = job.attempts + 1
        started_at = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            fresh = await claim.load_for_transition(db, job.id, job.lock_token)
            if fresh is None:
                logger.warning(
                    "lost ownership before running (reaped)",
                    extra={"extra_fields": {"job_id": str(job.id)}},
                )
                return
            fresh.status = JobStatus.running
            fresh.started_at = started_at
            execution = JobExecution(
                job_id=job.id,
                worker_id=self.worker_id,
                attempt_number=attempt,
                status=ExecutionStatus.running,
                started_at=started_at,
            )
            db.add(execution)
            await db.flush()
            # Keep the id: (job_id, attempt_number) is NOT unique — a job
            # reaped mid-run and re-claimed has another execution row with
            # the same attempt number, so looking it up again by attempt
            # could update the wrong (stale) row.
            execution_id = execution.id
            db.add(
                JobLog(
                    job_id=job.id,
                    execution_id=execution_id,
                    ts=started_at,
                    level=LogLevel.info,
                    message=f"Running handler '{job.handler}' (attempt {attempt}/{job.max_attempts})",
                )
            )
            await db.commit()

        # Execute the handler with no open DB transaction — job duration is
        # arbitrary (sleep, http_call, ...) and must never hold a connection.
        error_type: str | None = None
        error_message: str | None = None
        success = False
        loop = asyncio.get_running_loop()
        perf_start = loop.time()
        try:
            handler = HANDLERS.get(job.handler)
            if handler is None:
                raise ValueError(f"unknown handler: {job.handler}")
            ctx = JobContext(job_id=job.id, attempt=attempt, queue_id=job.queue_id, handler=job.handler)
            await handler(job.payload, ctx)
            success = True
        except Exception as exc:
            error_type = type(exc).__name__
            error_message = str(exc) or error_type
        elapsed = loop.time() - perf_start
        duration_ms = int(elapsed * 1000)

        obs.JOB_DURATION.labels(job.handler).observe(elapsed)
        obs.JOBS_EXECUTED.labels(job.handler, "success" if success else "failure").inc()

        result_status: JobStatus | None = None
        recent_logs: list[str] = []

        async with AsyncSessionLocal() as db:
            fresh = await claim.load_for_transition(db, job.id, job.lock_token)
            if fresh is None:
                logger.warning(
                    "lost ownership after running — discarding result",
                    extra={"extra_fields": {"job_id": str(job.id), "success": success}},
                )
                return

            execution = await db.get(JobExecution, execution_id)
            finished_at = datetime.now(timezone.utc)

            if success:
                fresh.status = JobStatus.completed
                fresh.finished_at = finished_at
                fresh.lock_token = None
                execution.status = ExecutionStatus.completed
                db.add(
                    JobLog(
                        job_id=job.id,
                        execution_id=execution_id,
                        ts=finished_at,
                        level=LogLevel.info,
                        message=f"Completed successfully in {duration_ms}ms",
                    )
                )
            else:
                fresh.attempts = attempt
                execution.status = ExecutionStatus.failed
                execution.error_type = error_type
                execution.error_message = error_message

                queue = await db.scalar(
                    select(Queue)
                    .where(Queue.id == fresh.queue_id)
                    .options(selectinload(Queue.retry_policy))
                )
                retry_policy = queue.retry_policy if queue else None
                result_status = await retry.apply_failure(
                    db, fresh, retry_policy, error_message or "unknown error"
                )

                if result_status == JobStatus.dead:
                    log_rows = (
                        await db.scalars(
                            select(JobLog.message)
                            .where(JobLog.job_id == job.id)
                            .order_by(JobLog.ts.desc())
                            .limit(10)
                        )
                    ).all()
                    recent_logs = list(reversed(log_rows))

                db.add(
                    JobLog(
                        job_id=job.id,
                        execution_id=execution_id,
                        ts=finished_at,
                        level=LogLevel.error,
                        message=f"{error_type}: {error_message} (-> {result_status.value})",
                    )
                )
                logger.info(
                    "job failed",
                    extra={"extra_fields": {
                        "job_id": str(job.id), "attempt": attempt,
                        "result": result_status.value, "error": error_message,
                    }},
                )

            execution.finished_at = finished_at
            execution.duration_ms = duration_ms
            await db.commit()

        # AI summary call happens with no open DB transaction/row lock — it's
        # a network round-trip to Groq that can take several seconds, and
        # this job is already in its terminal 'dead' state by this point, so
        # there's no contention to worry about holding up.
        if result_status == JobStatus.dead:
            summary = await ai_summary.summarize_failure(
                job.handler, error_message or "unknown error", recent_logs
            )
            if summary:
                async with AsyncSessionLocal() as db:
                    execution = await db.get(JobExecution, execution_id)
                    if execution is not None:
                        execution.ai_summary = summary
                        await db.commit()

    async def shutdown(self, grace_period_sec: float) -> None:
        self.shutting_down = True
        logger.info("draining — waiting up to %.0fs for in-flight jobs", grace_period_sec)

        async with AsyncSessionLocal() as db:
            worker = await db.get(Worker, self.worker_id)
            if worker is not None:
                worker.status = WorkerStatus.draining
                await db.commit()

        await self.runtime.wait_for_idle(timeout=grace_period_sec)
        await self.close_notify_listener()

        async with AsyncSessionLocal() as db:
            worker = await db.get(Worker, self.worker_id)
            if worker is not None:
                worker.status = WorkerStatus.dead
                worker.last_heartbeat_at = datetime.now(timezone.utc)
                await db.commit()

        logger.info("shutdown complete")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    if sys.platform == "win32":
        # The Proactor loop has no add_signal_handler; signal.signal handlers
        # run on the main thread between bytecodes, so hop back onto the loop
        # thread-safely. Without this, Ctrl+C killed the worker without the
        # graceful drain.
        def handler(_signum, _frame):
            loop.call_soon_threadsafe(stop_event.set)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
    else:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    obs.start_metrics_server(settings.worker_metrics_port)

    queue_names = [q.strip() for q in settings.worker_queues.split(",") if q.strip()]
    process = WorkerProcess(
        project_slug=settings.worker_project_slug,
        queue_names=queue_names,
        concurrency=settings.worker_concurrency,
    )
    await process.register()
    await process.setup_notify_listener(settings.async_database_url)

    stop_event = asyncio.Event()
    _install_signal_handlers(asyncio.get_running_loop(), stop_event)

    poll_task = asyncio.create_task(process.poll_loop(settings.worker_poll_interval_sec))
    heartbeat_task = asyncio.create_task(process.heartbeat_loop(settings.heartbeat_sec))

    await stop_event.wait()
    await process.shutdown(settings.worker_shutdown_grace_sec)

    poll_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(poll_task, heartbeat_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
