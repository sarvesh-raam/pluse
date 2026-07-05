import asyncio
import logging
import signal
import socket
import uuid
from datetime import datetime, timezone

import asyncpg
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.notify import CHANNEL as NOTIFY_CHANNEL
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
        stmt = select(Queue.id, Queue.name).where(Queue.project_id == self.project_id)
        if self.queue_names:
            stmt = stmt.where(Queue.name.in_(self.queue_names))
        rows = (await db.execute(stmt)).all()
        return [row.id for row in rows]

    async def register(self) -> None:
        async with AsyncSessionLocal() as db:
            self.project_id = await self._resolve_project(db)
            self.queue_ids = await self._refresh_queue_ids(db)

            worker = Worker(
                project_id=self.project_id,
                name=f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:6]}",
                hostname=socket.gethostname(),
                status=WorkerStatus.active,
                queues=self.queue_names or ["*"],
                concurrency=self.runtime.concurrency,
                last_heartbeat_at=datetime.now(timezone.utc),
            )
            db.add(worker)
            await db.commit()
            await db.refresh(worker)
            self.worker_id = worker.id

        logger.info(
            "worker registered",
            extra={"extra_fields": {
                "worker_id": str(self.worker_id),
                "project_id": str(self.project_id),
                "queue_count": len(self.queue_ids),
            }},
        )

    async def heartbeat_loop(self, interval_sec: float) -> None:
        while not self.shutting_down:
            await asyncio.sleep(interval_sec)
            try:
                async with AsyncSessionLocal() as db:
                    self.queue_ids = await self._refresh_queue_ids(db)
                    now = datetime.now(timezone.utc)
                    worker = await db.get(Worker, self.worker_id)
                    if worker is None:
                        continue
                    worker.last_heartbeat_at = now
                    worker.queues = self.queue_names or ["*"]
                    db.add(
                        WorkerHeartbeat(
                            worker_id=self.worker_id,
                            ts=now,
                            running_jobs=self.runtime.running_count,
                        )
                    )
                    await db.commit()
            except Exception:
                logger.exception("heartbeat failed")

    async def setup_notify_listener(self, database_url: str) -> None:
        """§10 bonus: event-driven execution. LISTEN on the channel the API/
        scheduler NOTIFY on enqueue/promote/reap, so poll_loop wakes up
        immediately instead of waiting out its normal interval. Polling
        stays as the fallback — if this connection can't be established
        (or drops), the worker still works correctly, just less promptly."""
        dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            self._notify_conn = await asyncpg.connect(dsn)
            await self._notify_conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
            logger.info("listening for %r notifications", NOTIFY_CHANNEL)
        except Exception:
            logger.exception("LISTEN/NOTIFY setup failed — falling back to polling only")
            self._notify_conn = None

    def _on_notify(self, _connection, _pid, _channel, _payload) -> None:
        self._wake_event.set()

    async def close_notify_listener(self) -> None:
        if self._notify_conn is not None:
            await self._notify_conn.close()

    async def poll_loop(self, interval_sec: float) -> None:
        while not self.shutting_down:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("poll iteration failed")
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=interval_sec)
            except asyncio.TimeoutError:
                pass
            self._wake_event.clear()

    async def _poll_once(self) -> None:
        for queue_id in list(self.queue_ids):
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
            db.add(
                JobLog(
                    job_id=job.id,
                    execution_id=execution.id,
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
        loop = asyncio.get_event_loop()
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
            error_message = str(exc)
        duration_ms = int((loop.time() - perf_start) * 1000)

        result_status: JobStatus | None = None
        execution_id: uuid.UUID | None = None
        recent_logs: list[str] = []

        async with AsyncSessionLocal() as db:
            fresh = await claim.load_for_transition(db, job.id, job.lock_token)
            if fresh is None:
                logger.warning(
                    "lost ownership after running — discarding result",
                    extra={"extra_fields": {"job_id": str(job.id), "success": success}},
                )
                return

            execution = await db.scalar(
                select(JobExecution).where(
                    JobExecution.job_id == job.id, JobExecution.attempt_number == attempt
                )
            )
            execution_id = execution.id
            finished_at = datetime.now(timezone.utc)

            if success:
                fresh.status = JobStatus.completed
                fresh.finished_at = finished_at
                fresh.lock_token = None
                execution.status = ExecutionStatus.completed
                db.add(
                    JobLog(
                        job_id=job.id,
                        execution_id=execution.id,
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
                        execution_id=execution.id,
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
        if result_status == JobStatus.dead and execution_id is not None:
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


async def main() -> None:
    configure_logging()
    settings = get_settings()

    queue_names = [q.strip() for q in settings.worker_queues.split(",") if q.strip()]
    process = WorkerProcess(
        project_slug=settings.worker_project_slug,
        queue_names=queue_names,
        concurrency=settings.worker_concurrency,
    )
    await process.register()
    await process.setup_notify_listener(settings.database_url)

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    import sys
    if sys.platform == "win32":
        # Windows does not support add_signal_handler, so we'll rely on KeyboardInterrupt
        pass
    else:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

    poll_task = asyncio.create_task(process.poll_loop(settings.worker_poll_interval_sec))
    heartbeat_task = asyncio.create_task(process.heartbeat_loop(settings.heartbeat_sec))

    await stop_event.wait()
    await process.shutdown(settings.worker_shutdown_grace_sec)

    poll_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(poll_task, heartbeat_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
