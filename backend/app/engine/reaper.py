from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.worker import Worker


async def reap_dead_workers(db: AsyncSession, visibility_timeout_sec: int) -> dict[str, int]:
    """§5.2 visibility-timeout / at-least-once guarantee.

    Two independent passes, deliberately not fused into one:
    1. Mark any not-yet-dead worker whose heartbeat has gone stale (or that
       crashed before ever sending one) as dead.
    2. Requeue every job still in claimed/running under *any* dead worker —
       not only workers just marked dead in pass 1. A worker can also mark
       itself dead directly as the final step of a graceful shutdown that
       ran out of its grace period (worker/main.py's shutdown()), and that
       job needs sweeping too. If this were "only reap on the transition
       tick", that job would be orphaned forever, since a worker already
       dead never matches a `status != dead` filter again.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=visibility_timeout_sec)

    stale = (
        await db.scalars(
            select(Worker).where(
                Worker.status != WorkerStatus.dead,
                Worker.last_heartbeat_at.is_not(None),
                Worker.last_heartbeat_at < cutoff,
            )
        )
    ).all()

    never_heartbeat = (
        await db.scalars(
            select(Worker).where(
                Worker.status != WorkerStatus.dead,
                Worker.last_heartbeat_at.is_(None),
                Worker.registered_at < cutoff,
            )
        )
    ).all()

    for worker in list(stale) + list(never_heartbeat):
        worker.status = WorkerStatus.dead

    requeue_stmt = (
        update(Job)
        .where(
            Job.status.in_([JobStatus.claimed, JobStatus.running]),
            Job.worker_id.in_(select(Worker.id).where(Worker.status == WorkerStatus.dead)),
        )
        .values(status=JobStatus.queued, worker_id=None, lock_token=None, updated_at=func.now())
    )
    result = await db.execute(requeue_stmt)

    return {
        "workers_reaped": len(stale) + len(never_heartbeat),
        "jobs_requeued": result.rowcount or 0,
    }
