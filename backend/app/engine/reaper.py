from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dispatcher import move_to_dlq
from app.models.enums import ExecutionStatus, JobStatus, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.worker import Worker

WORKER_LOST_ERROR = "WorkerLost"


async def reap_dead_workers(db: AsyncSession, visibility_timeout_sec: int) -> dict[str, int]:
    """§5.2 visibility-timeout / at-least-once guarantee.

    Two independent passes, deliberately not fused into one:
    1. Mark any not-yet-dead worker whose heartbeat has gone stale (or that
       crashed before ever sending one) as dead.
    2. Recover every job still in claimed/running under *any* dead worker —
       not only workers just marked dead in pass 1. A worker can also mark
       itself dead directly as the final step of a graceful shutdown that
       ran out of its grace period (worker/main.py's shutdown()), and that
       job needs sweeping too. If this were "only reap on the transition
       tick", that job would be orphaned forever, since a worker already
       dead never matches a `status != dead` filter again.

    A job whose handler had actually *started* (status running) when its
    worker died has used up an attempt: its execution row is closed out as
    failed and `attempts` is incremented, exactly as if the handler had
    raised. Without that, a job that reliably crashes its worker (OOM,
    segfault in a C extension, a chaos kill) would be requeued forever with
    attempts never moving, and could never reach the DLQ. A job that was
    only *claimed* never ran, so it's requeued without charging an attempt.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=visibility_timeout_sec)

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
    await db.flush()

    # SKIP LOCKED: a row locked right now belongs to a worker mid-transition
    # (load_for_transition) — leave it, it'll be picked up next tick if the
    # worker really is gone.
    orphans = (
        await db.scalars(
            select(Job)
            .where(
                Job.status.in_([JobStatus.claimed, JobStatus.running]),
                Job.worker_id.in_(select(Worker.id).where(Worker.status == WorkerStatus.dead)),
            )
            .with_for_update(skip_locked=True)
        )
    ).all()

    requeued = 0
    dead = 0
    for job in orphans:
        was_running = job.status == JobStatus.running
        error_message = "worker died while the job was running (heartbeat lost)"

        if was_running:
            await db.execute(
                update(JobExecution)
                .where(JobExecution.job_id == job.id, JobExecution.status == ExecutionStatus.running)
                .values(
                    status=ExecutionStatus.failed,
                    finished_at=now,
                    error_type=WORKER_LOST_ERROR,
                    error_message=error_message,
                )
            )
            job.attempts += 1

        if was_running and job.attempts >= job.max_attempts:
            await move_to_dlq(db, job, final_error=f"{WORKER_LOST_ERROR}: {error_message}")
            dead += 1
        else:
            job.status = JobStatus.queued
            job.worker_id = None
            job.lock_token = None
            job.claimed_at = None
            requeued += 1

    return {
        "workers_reaped": len(stale) + len(never_heartbeat),
        "jobs_requeued": requeued,
        "jobs_dead": dead,
    }
