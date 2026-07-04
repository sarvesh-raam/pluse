import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.notify import notify_jobs_available
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import ensure_role
from app.core.scoping import get_job_scoped, get_project_or_404, get_queue_scoped
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import JobStatus, JobType, MemberRole
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.models.user import User
from app.schemas.job import (
    JobBatchCreate,
    JobBatchOut,
    JobBatchProgress,
    JobCreate,
    JobExecutionOut,
    JobLogOut,
    JobOut,
    JobScheduleCreate,
    ScheduledJobOut,
)

try:
    from croniter import croniter
except ImportError:  # pragma: no cover
    croniter = None

router = APIRouter(prefix="/jobs", tags=["jobs"])

NON_CLAIMABLE_TERMINAL = {
    JobStatus.completed,
    JobStatus.cancelled,
}


def _initial_status_and_run_at(
    run_at: datetime | None, has_deps: bool
) -> tuple[JobStatus, datetime]:
    now = datetime.now(timezone.utc)

    if has_deps:
        # Dependency-gated jobs are promoted by the scheduler's deps step (§6.3)
        # once every referenced job is completed, independent of run_at. The
        # scheduler's time-based promote step (§6.1) must skip these rows —
        # otherwise a job with a past run_at would be queued before its deps
        # actually finish.
        return JobStatus.scheduled, run_at or now

    effective_run_at = run_at or now
    return (
        (JobStatus.queued, effective_run_at)
        if effective_run_at <= now
        else (JobStatus.scheduled, effective_run_at)
    )


async def _validate_depends_on(db: AsyncSession, depends_on: list[uuid.UUID] | None) -> None:
    if not depends_on:
        return
    count = await db.scalar(select(func.count()).select_from(Job).where(Job.id.in_(depends_on)))
    if count != len(set(depends_on)):
        raise UnprocessableError("One or more depends_on job ids do not exist")


@router.get("", response_model=Page[JobOut])
async def list_jobs(
    project_id: uuid.UUID,
    queue_id: uuid.UUID | None = None,
    job_status: JobStatus | None = Query(default=None, alias="status"),
    job_type: JobType | None = Query(default=None, alias="type"),
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[JobOut]:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    stmt = select(Job).join(Queue, Queue.id == Job.queue_id).where(Queue.project_id == project_id)
    if queue_id is not None:
        stmt = stmt.where(Job.queue_id == queue_id)
    if job_status is not None:
        stmt = stmt.where(Job.status == job_status)
    if job_type is not None:
        stmt = stmt.where(Job.type == job_type)

    stmt = apply_sort(stmt, Job, sort, order)
    return await paginate(db, stmt, params, JobOut)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    queue = await get_queue_scoped(db, body.queue_id, user, MemberRole.member)

    if body.idempotency_key:
        existing = await db.scalar(
            select(Job).where(
                Job.queue_id == queue.id, Job.idempotency_key == body.idempotency_key
            )
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing

    await _validate_depends_on(db, body.depends_on)

    job_status, run_at = _initial_status_and_run_at(body.run_at, bool(body.depends_on))
    max_attempts = body.max_attempts or (
        queue.retry_policy.max_attempts if queue.retry_policy else 3
    )

    job = Job(
        queue_id=queue.id,
        type=body.type,
        status=job_status,
        priority=body.priority,
        payload=body.payload,
        handler=body.handler,
        run_at=run_at,
        max_attempts=max_attempts,
        idempotency_key=body.idempotency_key,
        depends_on=body.depends_on,
    )
    db.add(job)
    try:
        if job_status == JobStatus.queued:
            await notify_jobs_available(db)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(Job).where(
                Job.queue_id == queue.id, Job.idempotency_key == body.idempotency_key
            )
        )
        if existing is None:
            raise ConflictError("Job could not be created due to a conflicting idempotency key")
        response.status_code = status.HTTP_200_OK
        return existing

    await db.refresh(job)
    return job


@router.post("/batch", response_model=JobBatchOut, status_code=status.HTTP_201_CREATED)
async def create_batch(
    body: JobBatchCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobBatchOut:
    queue = await get_queue_scoped(db, body.queue_id, user, MemberRole.member)

    batch_id = uuid.uuid4()
    job_status, run_at = _initial_status_and_run_at(body.run_at, has_deps=False)
    max_attempts_default = queue.retry_policy.max_attempts if queue.retry_policy else 3

    jobs = [
        Job(
            queue_id=queue.id,
            type=JobType.batch,
            status=job_status,
            priority=item.priority,
            payload=item.payload,
            handler=item.handler,
            run_at=run_at,
            max_attempts=max_attempts_default,
            idempotency_key=item.idempotency_key,
            batch_id=batch_id,
        )
        for item in body.jobs
    ]
    db.add_all(jobs)
    if job_status == JobStatus.queued:
        await notify_jobs_available(db)
    await db.commit()
    for job in jobs:
        await db.refresh(job)

    return JobBatchOut(batch_id=batch_id, jobs=jobs)


@router.get("/batch/{batch_id}", response_model=JobBatchProgress)
async def get_batch_progress(
    batch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobBatchProgress:
    first_job = await db.scalar(select(Job).where(Job.batch_id == batch_id).limit(1))
    if first_job is None:
        raise NotFoundError("Batch not found")

    await get_queue_scoped(db, first_job.queue_id, user, MemberRole.viewer)

    rows = (
        await db.execute(
            select(Job.status, func.count())
            .where(Job.batch_id == batch_id)
            .group_by(Job.status)
        )
    ).all()
    by_status = {s.value: count for s, count in rows}
    return JobBatchProgress(
        batch_id=batch_id, total=sum(by_status.values()), by_status=by_status
    )


@router.post("/schedule", response_model=ScheduledJobOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: JobScheduleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledJob:
    queue = await get_queue_scoped(db, body.queue_id, user, MemberRole.member)

    try:
        tz = ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:
        raise UnprocessableError(f"Unknown timezone: {body.timezone}")

    try:
        base = datetime.now(tz)
        next_run_at = croniter(body.cron_expr, base).get_next(datetime)
    except (ValueError, KeyError):
        raise UnprocessableError(f"Invalid cron expression: {body.cron_expr}")

    scheduled_job = ScheduledJob(
        queue_id=queue.id,
        cron_expr=body.cron_expr,
        timezone=body.timezone,
        handler=body.handler,
        payload=body.payload,
        next_run_at=next_run_at,
    )
    db.add(scheduled_job)
    await db.commit()
    await db.refresh(scheduled_job)
    return scheduled_job


@router.get("/schedule", response_model=list[ScheduledJobOut])
async def list_schedules(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledJob]:
    await get_queue_scoped(db, queue_id, user, MemberRole.viewer)
    rows = await db.scalars(
        select(ScheduledJob)
        .where(ScheduledJob.queue_id == queue_id)
        .order_by(ScheduledJob.next_run_at.asc())
    )
    return list(rows.all())


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job, _queue = await get_job_scoped(db, job_id, user, MemberRole.viewer)
    return job


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job, _queue = await get_job_scoped(db, job_id, user, MemberRole.member)

    if job.status not in (JobStatus.failed, JobStatus.dead):
        raise ForbiddenError(f"Cannot retry a job in status '{job.status.value}'")

    job.status = JobStatus.queued
    job.run_at = datetime.now(timezone.utc)
    job.attempts = 0
    job.worker_id = None
    job.lock_token = None
    job.claimed_at = None
    job.started_at = None
    job.finished_at = None

    await notify_jobs_available(db)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Job:
    job, _queue = await get_job_scoped(db, job_id, user, MemberRole.member)

    cancellable = {JobStatus.scheduled, JobStatus.queued, JobStatus.retrying}
    if job.status not in cancellable:
        raise ForbiddenError(f"Cannot cancel a job in status '{job.status.value}'")

    job.status = JobStatus.cancelled
    job.finished_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(job)
    return job


@router.get("/{job_id}/executions", response_model=list[JobExecutionOut])
async def list_executions(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[JobExecution]:
    await get_job_scoped(db, job_id, user, MemberRole.viewer)
    rows = await db.scalars(
        select(JobExecution)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.attempt_number.asc())
    )
    return list(rows.all())


@router.get("/{job_id}/logs", response_model=Page[JobLogOut])
async def list_logs(
    job_id: uuid.UUID,
    params: PaginationParams = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[JobLogOut]:
    await get_job_scoped(db, job_id, user, MemberRole.viewer)
    stmt = select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.ts.asc())
    return await paginate(db, stmt, params, JobLogOut)
