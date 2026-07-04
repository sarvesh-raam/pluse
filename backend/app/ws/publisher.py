import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.enums import ExecutionStatus, JobStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.queue import Queue
from app.models.worker import Worker
from app.ws.manager import manager

logger = logging.getLogger("pulse.ws")

POLL_INTERVAL_SEC = 2.0


class EventPublisher:
    def __init__(self) -> None:
        self._last_check: dict[uuid.UUID, datetime] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        logger.info("ws publisher started", extra={"extra_fields": {"interval_sec": POLL_INTERVAL_SEC}})
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("ws publisher tick failed")
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _tick(self) -> None:
        project_ids = manager.active_project_ids()
        if not project_ids:
            return

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            for project_id in project_ids:
                since = self._last_check.get(
                    project_id, now - timedelta(seconds=POLL_INTERVAL_SEC * 2)
                )
                await self._broadcast_job_updates(db, project_id, since)
                await self._broadcast_worker_updates(db, project_id, since)
                await self._broadcast_queue_stats(db, project_id)
                await self._broadcast_metrics_tick(db, project_id)
                self._last_check[project_id] = now

    async def _broadcast_job_updates(
        self, db: AsyncSession, project_id: uuid.UUID, since: datetime
    ) -> None:
        rows = (
            await db.execute(
                select(Job.id, Job.status, Job.queue_id, Job.updated_at)
                .join(Queue, Queue.id == Job.queue_id)
                .where(Queue.project_id == project_id, Job.updated_at > since)
                .order_by(Job.updated_at.asc())
                .limit(200)
            )
        ).all()
        for row in rows:
            await manager.broadcast(
                project_id,
                {
                    "type": "job.updated",
                    "data": {
                        "id": str(row.id),
                        "status": row.status.value,
                        "queue_id": str(row.queue_id),
                    },
                },
            )

    async def _broadcast_worker_updates(
        self, db: AsyncSession, project_id: uuid.UUID, since: datetime
    ) -> None:
        workers = (
            await db.scalars(
                select(Worker).where(
                    Worker.project_id == project_id, Worker.last_heartbeat_at > since
                )
            )
        ).all()
        for worker in workers:
            await manager.broadcast(
                project_id,
                {
                    "type": "worker.updated",
                    "data": {
                        "id": str(worker.id),
                        "name": worker.name,
                        "status": worker.status.value,
                        "last_heartbeat_at": (
                            worker.last_heartbeat_at.isoformat()
                            if worker.last_heartbeat_at
                            else None
                        ),
                    },
                },
            )

    async def _broadcast_queue_stats(self, db: AsyncSession, project_id: uuid.UUID) -> None:
        queues = (await db.scalars(select(Queue).where(Queue.project_id == project_id))).all()
        for queue in queues:
            depth = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue.id, Job.status == JobStatus.queued)
            )
            running = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.queue_id == queue.id,
                    Job.status.in_([JobStatus.claimed, JobStatus.running]),
                )
            )
            await manager.broadcast(
                project_id,
                {
                    "type": "queue.stats",
                    "data": {
                        "queue_id": str(queue.id),
                        "name": queue.name,
                        "depth": depth or 0,
                        "running": running or 0,
                        "is_paused": queue.is_paused,
                    },
                },
            )

    async def _broadcast_metrics_tick(self, db: AsyncSession, project_id: uuid.UUID) -> None:
        one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        base = (
            select(func.count())
            .select_from(JobExecution)
            .join(Job, Job.id == JobExecution.job_id)
            .join(Queue, Queue.id == Job.queue_id)
            .where(Queue.project_id == project_id, JobExecution.finished_at >= one_min_ago)
        )
        completed = await db.scalar(base.where(JobExecution.status == ExecutionStatus.completed))
        failed = await db.scalar(base.where(JobExecution.status == ExecutionStatus.failed))

        await manager.broadcast(
            project_id,
            {
                "type": "metrics.tick",
                "data": {
                    "completed_last_min": completed or 0,
                    "failed_last_min": failed or 0,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            },
        )


publisher = EventPublisher()
