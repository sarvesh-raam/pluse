import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core import observability as obs
from app.core.logging import configure_logging
from app.core.notify import notify_jobs_available
from app.core.ratelimit import registry as rate_limiter
from app.db import AsyncSessionLocal
from app.engine import reaper
from app.models.enums import JobStatus, JobType, WorkerStatus
from app.models.job import Job
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat

logger = logging.getLogger("pulse.scheduler")

DEFAULT_MAX_ATTEMPTS = 3

# Leader election for running the scheduler as several replicas (e.g. a
# Kubernetes Deployment with replicas>1 for availability). Each tick runs in
# one transaction that first tries a transaction-scoped advisory lock; only
# the replica that gets it does any work, the rest skip that tick. If the
# leader dies, its lock is released with its connection and another replica
# takes over on its very next tick — no lease/TTL bookkeeping needed.
SCHEDULER_LOCK_KEY = 0x50554C53  # "PULS"
REAPER_LOCK_KEY = 0x50554C52  # "PULR"

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

    now = datetime.now(timezone.utc)
    spawned = 0
    for sched in due:
        try:
            tz = ZoneInfo(sched.timezone)
            # Advance from max(next_run_at, now), not from next_run_at: after
            # scheduler downtime, stepping one interval per tick would spawn
            # a burst of catch-up jobs (one for every missed slot). Missed
            # runs collapse into the single run spawned below instead.
            base = max(sched.next_run_at, now).astimezone(tz)
            next_run_at = croniter(sched.cron_expr, base).get_next(datetime)
        except Exception:
            # One broken template (bad tz / cron written straight to the DB)
            # must not fail the tick for every other schedule — deactivate it.
            logger.exception(
                "invalid schedule — deactivating",
                extra={"extra_fields": {"scheduled_job_id": str(sched.id)}},
            )
            sched.is_active = False
            continue

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
        sched.next_run_at = next_run_at
        sched.last_run_at = now
        spawned += 1

    return spawned


async def resolve_dependencies(db: AsyncSession) -> int:
    """§6 step 3: for scheduled jobs with depends_on, promote to queued once
    every referenced job is completed; cancel if any referenced job is dead
    or cancelled (a prerequisite that can never succeed makes the dependent
    unrunnable too)."""
    pending = (
        await db.scalars(
            select(Job).where(
                Job.status == JobStatus.scheduled,
                Job.depends_on.is_not(None),
                func.array_length(Job.depends_on, 1) > 0,
            )
        )
    ).all()
    if not pending:
        return 0

    # one query for every prerequisite of every pending job, instead of one
    # query per pending job
    all_dep_ids = {dep_id for job in pending for dep_id in job.depends_on}
    status_by_id = dict(
        (await db.execute(select(Job.id, Job.status).where(Job.id.in_(all_dep_ids)))).all()
    )

    count = 0
    for job in pending:
        wanted = set(job.depends_on)
        dep_statuses = [status_by_id[d] for d in wanted if d in status_by_id]

        if len(dep_statuses) < len(wanted):
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


async def _try_lock(db: AsyncSession, key: int) -> bool:
    return bool(await db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key}))


async def tick(db: AsyncSession) -> dict[str, int]:
    if not await _try_lock(db, SCHEDULER_LOCK_KEY):
        await db.rollback()
        obs.SCHED_LEADER.set(0)
        return {"promoted": 0, "spawned": 0, "deps_resolved": 0}
    obs.SCHED_LEADER.set(1)

    promoted = await promote_due_jobs(db)
    spawned = await promote_cron_jobs(db)
    deps_resolved = await resolve_dependencies(db)
    if promoted or spawned or deps_resolved:
        await notify_jobs_available(db)
    await db.commit()

    obs.SCHED_PROMOTED.labels("due").inc(promoted)
    obs.SCHED_PROMOTED.labels("cron").inc(spawned)
    obs.SCHED_PROMOTED.labels("dependencies").inc(deps_resolved)
    return {"promoted": promoted, "spawned": spawned, "deps_resolved": deps_resolved}


async def prune_telemetry(
    db: AsyncSession, heartbeat_retention_hours: int, dead_worker_retention_hours: int
) -> dict[str, int]:
    """worker_heartbeats gets a row per worker every few seconds and every
    worker restart registers a new workers row — without pruning, both grow
    forever. Jobs/executions reference workers with ON DELETE SET NULL, so
    deleting long-dead workers never loses job history."""
    now = datetime.now(timezone.utc)
    heartbeats = await db.execute(
        delete(WorkerHeartbeat).where(
            WorkerHeartbeat.ts < now - timedelta(hours=heartbeat_retention_hours)
        )
    )
    workers = await db.execute(
        delete(Worker).where(
            Worker.status == WorkerStatus.dead,
            Worker.last_heartbeat_at < now - timedelta(hours=dead_worker_retention_hours),
        )
    )
    return {
        "heartbeats_pruned": heartbeats.rowcount or 0,
        "workers_pruned": workers.rowcount or 0,
    }


async def run_forever() -> None:
    settings = get_settings()
    logger.info("scheduler started", extra={"extra_fields": {"tick_sec": settings.sched_tick_sec}})
    loop = asyncio.get_running_loop()

    while True:
        started = loop.time()
        try:
            async with AsyncSessionLocal() as db:
                with obs.SCHED_TICK_SECONDS.time():
                    stats = await tick(db)
                if any(stats.values()):
                    logger.info("scheduler tick", extra={"extra_fields": stats})
        except Exception:
            logger.exception("scheduler tick failed")

        # keep a steady cadence regardless of how long the tick took
        await asyncio.sleep(max(settings.sched_tick_sec - (loop.time() - started), 0.05))


async def run_reaper_forever() -> None:
    settings = get_settings()
    logger.info(
        "reaper started",
        extra={"extra_fields": {"tick_sec": settings.reaper_tick_sec,
                                 "visibility_timeout_sec": settings.visibility_timeout_sec}},
    )
    # pruning is cheap but pointless every few seconds — about once a minute
    prune_every = max(60 // max(settings.reaper_tick_sec, 1), 1)

    ticks = 0
    while True:
        try:
            async with AsyncSessionLocal() as db:
                if await _try_lock(db, REAPER_LOCK_KEY):
                    stats = await reaper.reap_dead_workers(db, settings.visibility_timeout_sec)
                    if stats["jobs_requeued"]:
                        await notify_jobs_available(db)
                    if ticks % prune_every == 0:
                        stats.update(
                            await prune_telemetry(
                                db,
                                settings.heartbeat_retention_hours,
                                settings.dead_worker_retention_hours,
                            )
                        )
                    await db.commit()

                    obs.REAPER_WORKERS_REAPED.inc(stats["workers_reaped"])
                    obs.REAPER_JOBS_RECOVERED.labels("requeued").inc(stats["jobs_requeued"])
                    obs.REAPER_JOBS_RECOVERED.labels("dead").inc(stats["jobs_dead"])
                    if stats["workers_reaped"] or stats["jobs_requeued"] or stats["jobs_dead"]:
                        logger.info("reaper swept dead workers", extra={"extra_fields": stats})
                else:
                    await db.rollback()
        except Exception:
            logger.exception("reaper tick failed")

        ticks += 1
        await asyncio.sleep(settings.reaper_tick_sec)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    obs.start_metrics_server(settings.scheduler_metrics_port)
    await asyncio.gather(run_forever(), run_reaper_forever())


if __name__ == "__main__":
    asyncio.run(main())
