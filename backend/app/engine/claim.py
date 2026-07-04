import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

# The single most important query in the system (§5.1). FOR UPDATE OF j
# SKIP LOCKED guarantees two workers never claim the same row: if one
# worker's transaction already has a row locked, a concurrent claimer
# simply skips past it instead of blocking on it. "OF j" scopes the row
# lock to jobs only — queues is joined only to read concurrency_limit and
# is_paused, and must never be locked by this statement.
_CLAIM_SQL = text(
    """
    WITH capacity AS (
        SELECT q.concurrency_limit - COUNT(j2.id) AS free_slots
        FROM queues q
        LEFT JOIN jobs j2
            ON j2.queue_id = q.id AND j2.status IN ('claimed', 'running')
        WHERE q.id = :queue_id AND q.is_paused = false
        GROUP BY q.concurrency_limit
    ),
    claimable AS (
        SELECT j.id
        FROM jobs j
        WHERE j.queue_id = :queue_id
          AND j.status = 'queued'
          AND j.run_at <= now()
        ORDER BY j.priority DESC, j.run_at ASC
        FOR UPDATE OF j SKIP LOCKED
        LIMIT LEAST(:limit, GREATEST((SELECT free_slots FROM capacity), 0))
    )
    UPDATE jobs
    SET status = 'claimed',
        worker_id = :worker_id,
        lock_token = gen_random_uuid(),
        claimed_at = now(),
        updated_at = now()
    FROM claimable
    WHERE jobs.id = claimable.id
    RETURNING jobs.id
    """
)

# Serializes the capacity-check + claim per queue across all workers.
# FOR UPDATE SKIP LOCKED alone only prevents two workers from claiming the
# *same* row — it says nothing about the aggregate claimed+running count
# staying under concurrency_limit. Two workers could each read "3 free
# slots" from their own snapshot and each claim 3, blowing past the
# ceiling. A transaction-scoped advisory lock keyed by queue_id makes the
# read-then-claim atomic for that queue without blocking claims against
# any *other* queue.
_QUEUE_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtext(:key), 0)")


async def claim_jobs(
    db: AsyncSession, queue_id: uuid.UUID, worker_id: uuid.UUID, limit: int
) -> list[Job]:
    if limit <= 0:
        return []

    await db.execute(_QUEUE_LOCK_SQL, {"key": str(queue_id)})
    result = await db.execute(
        _CLAIM_SQL, {"queue_id": queue_id, "worker_id": worker_id, "limit": limit}
    )
    claimed_ids = [row.id for row in result.fetchall()]
    await db.commit()

    if not claimed_ids:
        return []

    jobs = (await db.scalars(select(Job).where(Job.id.in_(claimed_ids)))).all()
    return list(jobs)


async def load_for_transition(
    db: AsyncSession, job_id: uuid.UUID, lock_token: uuid.UUID
) -> Job | None:
    """Row-lock the job for a state transition, guarded by lock_token so a
    worker that's been reaped (lock_token reset to NULL, or reassigned to a
    new claimant) can't clobber state written since. Holding the row lock
    until commit also blocks a concurrent reaper sweep from resetting this
    row out from under an in-flight transition — once we commit, the
    reaper's own guard (status IN ('claimed','running')) will simply no
    longer match if we've already moved the job to a terminal/retry state.
    """
    return await db.scalar(
        select(Job).where(Job.id == job_id, Job.lock_token == lock_token).with_for_update()
    )
