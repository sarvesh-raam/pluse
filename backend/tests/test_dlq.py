from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import retry
from app.models.dead_letter import DeadLetterEntry
from app.models.enums import JobStatus, JobType
from app.models.job import Job


async def test_job_exceeding_max_attempts_lands_in_dlq_exactly_once(db_session: AsyncSession, seeded: dict):
    """§5.3/§5.4: once attempts >= max_attempts, the job must move to 'dead'
    and produce exactly one dead_letter_queue row in the same transaction."""
    queue = seeded["queue"]
    job = Job(
        queue_id=queue.id,
        type=JobType.immediate,
        status=JobStatus.running,
        handler="fail_n_times",
        payload={"fail_until": 99},
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        attempts=3,  # already exhausted
    )
    db_session.add(job)
    await db_session.flush()

    result_status = await retry.apply_failure(db_session, job, retry_policy=None, error_message="boom")
    await db_session.commit()

    assert result_status == JobStatus.dead
    assert job.status == JobStatus.dead

    entries = (
        await db_session.scalars(select(DeadLetterEntry).where(DeadLetterEntry.job_id == job.id))
    ).all()
    assert len(entries) == 1
    assert entries[0].total_attempts == 3
    assert entries[0].final_error == "boom"


async def test_job_under_max_attempts_retries_instead_of_dlq(db_session: AsyncSession, seeded: dict):
    queue = seeded["queue"]
    job = Job(
        queue_id=queue.id,
        type=JobType.immediate,
        status=JobStatus.running,
        handler="fail_n_times",
        payload={"fail_until": 99},
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        attempts=1,
    )
    db_session.add(job)
    await db_session.flush()

    result_status = await retry.apply_failure(db_session, job, retry_policy=None, error_message="boom")
    await db_session.commit()

    assert result_status == JobStatus.retrying
    assert job.status == JobStatus.retrying
    assert job.run_at > datetime.now(timezone.utc)

    entries = (
        await db_session.scalars(select(DeadLetterEntry).where(DeadLetterEntry.job_id == job.id))
    ).all()
    assert len(entries) == 0
