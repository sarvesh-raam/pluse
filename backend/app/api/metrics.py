import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnprocessableError
from app.core.rbac import ensure_role
from app.core.scoping import get_project_or_404
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import ExecutionStatus, JobStatus, MemberRole, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker
from app.schemas.metrics import MetricsOverview, QueueMetric, ThroughputBucket, ThroughputResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])

_WINDOW_RE = re.compile(r"^(\d+)([mhd])$")


def _parse_window(window: str) -> tuple[timedelta, str]:
    match = _WINDOW_RE.match(window)
    if not match:
        raise UnprocessableError(f"invalid window {window!r} — expected e.g. 30m, 1h, 24h, 7d")

    value, unit = int(match.group(1)), match.group(2)
    delta = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}[unit]

    seconds = delta.total_seconds()
    if seconds <= 3600 * 2:
        bucket_size = "minute"
    elif seconds <= 3600 * 24 * 3:
        bucket_size = "hour"
    else:
        bucket_size = "day"
    return delta, bucket_size


@router.get("/overview", response_model=MetricsOverview)
async def metrics_overview(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MetricsOverview:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    now = datetime.now(timezone.utc)
    five_min_ago = now - timedelta(minutes=5)
    one_hour_ago = now - timedelta(hours=1)

    exec_base = (
        select(func.count())
        .select_from(JobExecution)
        .join(Job, Job.id == JobExecution.job_id)
        .join(Queue, Queue.id == Job.queue_id)
        .where(Queue.project_id == project_id)
    )
    completed_5m = await db.scalar(
        exec_base.where(JobExecution.status == ExecutionStatus.completed, JobExecution.finished_at >= five_min_ago)
    ) or 0
    completed_1h = await db.scalar(
        exec_base.where(JobExecution.status == ExecutionStatus.completed, JobExecution.finished_at >= one_hour_ago)
    ) or 0
    failed_1h = await db.scalar(
        exec_base.where(JobExecution.status == ExecutionStatus.failed, JobExecution.finished_at >= one_hour_ago)
    ) or 0

    terminal = completed_1h + failed_1h
    success_rate = completed_1h / terminal if terminal > 0 else None

    active_workers = await db.scalar(
        select(func.count())
        .select_from(Worker)
        .where(Worker.project_id == project_id, Worker.status == WorkerStatus.active)
    ) or 0

    queue_depth_total = await db.scalar(
        select(func.count())
        .select_from(Job)
        .join(Queue, Queue.id == Job.queue_id)
        .where(Queue.project_id == project_id, Job.status == JobStatus.queued)
    ) or 0

    return MetricsOverview(
        project_id=project_id,
        throughput_per_min=completed_5m / 5.0,
        success_rate=success_rate,
        active_workers=active_workers,
        queue_depth_total=queue_depth_total,
    )


@router.get("/throughput", response_model=ThroughputResponse)
async def metrics_throughput(
    project_id: uuid.UUID,
    window: str = "1h",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThroughputResponse:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    delta, bucket_size = _parse_window(window)
    since = datetime.now(timezone.utc) - delta

    bucket = func.date_trunc(bucket_size, JobExecution.finished_at).label("bucket")
    rows = (
        await db.execute(
            select(
                bucket,
                func.count().filter(JobExecution.status == ExecutionStatus.completed).label("completed"),
                func.count().filter(JobExecution.status == ExecutionStatus.failed).label("failed"),
            )
            .select_from(JobExecution)
            .join(Job, Job.id == JobExecution.job_id)
            .join(Queue, Queue.id == Job.queue_id)
            .where(
                Queue.project_id == project_id,
                JobExecution.finished_at.is_not(None),
                JobExecution.finished_at >= since,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()

    return ThroughputResponse(
        project_id=project_id,
        window=window,
        bucket_size=bucket_size,
        buckets=[
            ThroughputBucket(bucket_start=row.bucket, completed=row.completed, failed=row.failed)
            for row in rows
        ],
    )


@router.get("/queues", response_model=list[QueueMetric])
async def metrics_queues(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QueueMetric]:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    queues = (await db.scalars(select(Queue).where(Queue.project_id == project_id))).all()

    results: list[QueueMetric] = []
    for queue in queues:
        depth = await db.scalar(
            select(func.count()).select_from(Job).where(Job.queue_id == queue.id, Job.status == JobStatus.queued)
        ) or 0
        running = await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.queue_id == queue.id, Job.status.in_([JobStatus.claimed, JobStatus.running]))
        ) or 0
        completed = await db.scalar(
            select(func.count()).select_from(Job).where(Job.queue_id == queue.id, Job.status == JobStatus.completed)
        ) or 0
        failed_or_dead = await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.queue_id == queue.id, Job.status.in_([JobStatus.failed, JobStatus.dead]))
        ) or 0
        terminal = completed + failed_or_dead
        success_rate = completed / terminal if terminal > 0 else None

        avg_duration = await db.scalar(
            select(func.avg(JobExecution.duration_ms))
            .select_from(JobExecution)
            .join(Job, Job.id == JobExecution.job_id)
            .where(
                Job.queue_id == queue.id,
                JobExecution.status == ExecutionStatus.completed,
                JobExecution.duration_ms.is_not(None),
            )
        )

        results.append(
            QueueMetric(
                queue_id=queue.id,
                name=queue.name,
                depth=depth,
                running=running,
                success_rate=success_rate,
                avg_duration_ms=float(avg_duration) if avg_duration is not None else None,
            )
        )

    return results
