from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.dead_letter import DeadLetterEntry
from app.models.enums import JobStatus
from app.models.job import Job


async def move_to_dlq(db: AsyncSession, job: Job, final_error: str) -> DeadLetterEntry:
    """Transactionally move a job to the dead letter queue: insert the DLQ
    row and mark the job dead in the same unit of work (caller commits)."""
    entry = DeadLetterEntry(
        job_id=job.id,
        queue_id=job.queue_id,
        payload=job.payload,
        final_error=final_error,
        total_attempts=job.attempts,
    )
    db.add(entry)

    job.status = JobStatus.dead
    job.finished_at = datetime.now(timezone.utc)
    job.worker_id = None
    job.lock_token = None
    return entry


async def replay_from_dlq(db: AsyncSession, dlq_entry: DeadLetterEntry) -> Job:
    """Requeue the original job for a DLQ entry and mark the entry replayed."""
    job = await db.get(Job, dlq_entry.job_id)
    if job is None:
        raise NotFoundError("Original job no longer exists")

    job.status = JobStatus.queued
    job.attempts = 0
    job.run_at = datetime.now(timezone.utc)
    job.worker_id = None
    job.lock_token = None
    job.claimed_at = None
    job.started_at = None
    job.finished_at = None

    dlq_entry.replayed_at = datetime.now(timezone.utc)
    return job
