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
from app.db import AsyncSessionLocal
from app.models.enums import JobStatus, JobType
from app.models.job import Job
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob

logger = logging.getLogger("pulse.scheduler")

DEFAULT_MAX_ATTEMPTS = 3

_no_deps = or_(Job.depends_on.is_(None), func.array_length(Job.depends_on, 1).is_(None))


async def promote_due_jobs(db: AsyncSession) -> int:
    """§6 step 1: flip due 'scheduled' jobs (with no unresolved deps) and due
    'retrying' jobs to 'queued'. Deps-gated 'scheduled' jobs are excluded here
    — they're promoted exclusively by resolve_dependencies() once every
    referenced job completes, regardless of run_at."""
    stmt = (
        update(Job)
        .where(
            Job.run_at <= func.now(),
            or_(
                and_(Job.status == JobStatus.scheduled, _no_deps),
                Job.status == JobStatus.retrying,
            ),
        )
        .values(status=JobStatus.queued, updated_at=func.now())
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


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


async def main() -> None:
    configure_logging()
    await run_forever()


if __name__ == "__main__":
    asyncio.run(main())
