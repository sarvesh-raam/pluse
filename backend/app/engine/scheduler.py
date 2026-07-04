import asyncio
import logging
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.notify import notify_jobs_available
from app.core.ratelimit import registry as rate_limiter
from app.db import AsyncSessionLocal
from app.engine import reaper
from app.models.enums import JobStatus, JobType
from app.models.job import Job
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob

logger = logging.getLogger("pulse.scheduler")

DEFAULT_MAX_ATTEMPTS = 3

_no_deps = or_(Job.depends_on.is_(None), func.array_length(Job.depends_on, 1).is_(None))


_DUE_FILTER = or_(
    and_(Job.status == JobStatus.scheduled, _no_deps),
    Job.status == JobStatus.retrying,
)


async def _promote_rate_limited_queue(db: AsyncSession, queue_id, rate_per_sec: float) -> int:
    """§10 bonus: rate limiting. A queue with rate_limit_per_sec set can only
    have that many jobs promoted from waiting -> queued per second, via a
    per-queue token bucket — independent of concurrency_limit, which caps
    how many run *simultaneously* rather than how fast new ones start."""
    allowance = rate_limiter.take_available(queue_id, rate_per_sec)
    if allowance <= 0:
        return 0

    subq = (
        select(Job.id)
        .where(Job.queue_id == queue_id, Job.run_at <= func.now(), _DUE_FILTER)
        .order_by(Job.priority.desc(), Job.run_at.asc())
        .limit(allowance)
    )
    stmt = (
        update(Job)
        .where(Job.id.in_(subq))
        .values(status=JobStatus.queued, updated_at=func.now())
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def promote_due_jobs(db: AsyncSession) -> int:
    """§6 step 1: flip due 'scheduled' jobs (with no unresolved deps) and due
    'retrying' jobs to 'queued'. Deps-gated 'scheduled' jobs are excluded here
    — they're promoted exclusively by resolve_dependencies() once every
    referenced job completes, regardless of run_at."""
    rate_limited = (
        await db.execute(
            select(Queue.id, Queue.rate_limit_per_sec).where(Queue.rate_limit_per_sec.is_not(None))
        )
    ).all()

    total = 0
    for queue_id, rate_per_sec in rate_limited:
        total += await _promote_rate_limited_queue(db, queue_id, rate_per_sec)

    rate_limited_ids = [row.id for row in rate_limited]
    stmt = update(Job).where(Job.run_at <= func.now(), _DUE_FILTER)
    if rate_limited_ids:
        stmt = stmt.where(Job.queue_id.not_in(rate_limited_ids))
    stmt = stmt.values(status=JobStatus.queued, updated_at=func.now())

    result = await db.execute(stmt)
    total += result.rowcount or 0
    return total


async def promote_cron_jobs(db: AsyncSession) -> int:
    """§6 step 2: for each active scheduled_jobs template that's due, spawn a
    new jobs row and advance next_run_at via croniter."""
    due = (
        await db.scalars(
            select(ScheduledJob)
            .where(ScheduledJob.is_active.is_(True), ScheduledJob.next_run_at <= func.now())
            .options(selectinload(ScheduledJob.queue).selectinload(Queue.retry_policy))
        )
    ).all()

    for sched in due:
        max_attempts = (
            sched.queue.retry_policy.max_attempts
            if sched.queue.retry_policy
            else DEFAULT_MAX_ATTEMPTS
        )
        db.add(
            Job(
                queue_id=sched.queue_id,
                type=JobType.recurring,
                status=JobStatus.queued,
                priority=sched.queue.priority_default,
                payload=sched.payload,
                handler=sched.handler,
                run_at=sched.next_run_at,
                max_attempts=max_attempts,
                cron_expr=sched.cron_expr,
                scheduled_job_id=sched.id,
            )
        )

        tz = ZoneInfo(sched.timezone)
        base = sched.next_run_at.astimezone(tz)
        sched.next_run_at = croniter(sched.cron_expr, base).get_next(datetime)
        sched.last_run_at = datetime.now(timezone.utc)

    return len(due)


async def resolve_dependencies(db: AsyncSession) -> int:
    """§6 step 3: for scheduled jobs with depends_on, promote to queued once
    every referenced job is completed; cancel if any referenced job is dead
    or cancelled (a prerequisite that can never succeed makes the dependent
    unrunnable too)."""
    pending = (
        await db.scalars(
            select(Job).where(Job.status == JobStatus.scheduled, Job.depends_on.is_not(None))
        )
    ).all()

    count = 0
    for job in pending:
        if not job.depends_on:
            continue

        dep_statuses = (
            await db.execute(select(Job.status).where(Job.id.in_(job.depends_on)))
        ).scalars().all()

        if len(dep_statuses) < len(set(job.depends_on)):
            # a referenced job no longer exists (e.g. its queue was deleted);
            # leave the dependent gated rather than guessing at intent.
            continue

        if any(s in (JobStatus.dead, JobStatus.cancelled) for s in dep_statuses):
            job.status = JobStatus.cancelled
            job.finished_at = datetime.now(timezone.utc)
            count += 1
        elif all(s == JobStatus.completed for s in dep_statuses):
            job.status = JobStatus.queued
            job.run_at = datetime.now(timezone.utc)
            count += 1

    return count


async def tick(db: AsyncSession) -> dict[str, int]:
    promoted = await promote_due_jobs(db)
    spawned = await promote_cron_jobs(db)
    deps_resolved = await resolve_dependencies(db)
    if promoted or spawned or deps_resolved:
        await notify_jobs_available(db)
    await db.commit()
    return {"promoted": promoted, "spawned": spawned, "deps_resolved": deps_resolved}


async def run_forever() -> None:
    settings = get_settings()
    logger.info("scheduler started", extra={"extra_fields": {"tick_sec": settings.sched_tick_sec}})

    while True:
        try:
            async with AsyncSessionLocal() as db:
                stats = await tick(db)
                if any(stats.values()):
                    logger.info("scheduler tick", extra={"extra_fields": stats})
        except Exception:
            logger.exception("scheduler tick failed")

        await asyncio.sleep(settings.sched_tick_sec)


async def run_reaper_forever() -> None:
    settings = get_settings()
    logger.info(
        "reaper started",
        extra={"extra_fields": {"tick_sec": settings.reaper_tick_sec,
                                 "visibility_timeout_sec": settings.visibility_timeout_sec}},
    )

    while True:
        try:
            async with AsyncSessionLocal() as db:
                stats = await reaper.reap_dead_workers(db, settings.visibility_timeout_sec)
                if stats["jobs_requeued"]:
                    await notify_jobs_available(db)
                await db.commit()
                if stats["workers_reaped"]:
                    logger.info("reaper swept dead workers", extra={"extra_fields": stats})
        except Exception:
            logger.exception("reaper tick failed")

        await asyncio.sleep(settings.reaper_tick_sec)


async def main() -> None:
    configure_logging()
    await asyncio.gather(run_forever(), run_reaper_forever())


if __name__ == "__main__":
    asyncio.run(main())
