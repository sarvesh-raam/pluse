import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import reaper
from app.models.enums import JobStatus, JobType, WorkerStatus
from app.models.job import Job
from app.models.worker import Worker


async def test_stale_heartbeat_job_returns_to_queued(db_session: AsyncSession, seeded: dict):
    """§5.2: a job held by a worker whose heartbeat has gone stale must be
    reset to queued (worker_id/lock_token cleared) and the worker marked dead."""
    queue = seeded["queue"]
    project = seeded["project"]

    stale_worker = Worker(
        project_id=project.id,
        name="stale-worker",
        hostname="host-a",
        status=WorkerStatus.active,
        queues=["*"],
        concurrency=5,
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=60),
    )
    db_session.add(stale_worker)
    await db_session.flush()

    job = Job(
        queue_id=queue.id,
        type=JobType.immediate,
        status=JobStatus.running,
        handler="sleep",
        payload={"seconds": 5},
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        worker_id=stale_worker.id,
        lock_token=uuid.uuid4(),
    )
    db_session.add(job)
    await db_session.commit()

    stats = await reaper.reap_dead_workers(db_session, visibility_timeout_sec=30)
    await db_session.commit()

    assert stats["workers_reaped"] == 1
    assert stats["jobs_requeued"] == 1

    await db_session.refresh(job)
    await db_session.refresh(stale_worker)
    assert job.status == JobStatus.queued
    assert job.worker_id is None
    assert job.lock_token is None
    assert stale_worker.status == WorkerStatus.dead


async def test_fresh_heartbeat_job_is_not_reaped(db_session: AsyncSession, seeded: dict):
    queue = seeded["queue"]
    project = seeded["project"]

    fresh_worker = Worker(
        project_id=project.id,
        name="fresh-worker",
        hostname="host-b",
        status=WorkerStatus.active,
        queues=["*"],
        concurrency=5,
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    db_session.add(fresh_worker)
    await db_session.flush()

    job = Job(
        queue_id=queue.id,
        type=JobType.immediate,
        status=JobStatus.running,
        handler="sleep",
        payload={"seconds": 5},
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        worker_id=fresh_worker.id,
        lock_token=uuid.uuid4(),
    )
    db_session.add(job)
    await db_session.commit()

    stats = await reaper.reap_dead_workers(db_session, visibility_timeout_sec=30)
    await db_session.commit()

    assert stats["workers_reaped"] == 0
    assert stats["jobs_requeued"] == 0

    await db_session.refresh(job)
    assert job.status == JobStatus.running


async def test_orphaned_job_under_an_already_dead_worker_is_still_swept(
    db_session: AsyncSession, seeded: dict
):
    """A worker can also be marked dead directly (e.g. by its own graceful
    shutdown exceeding its grace period), not just by the reaper's own
    stale-heartbeat detection. The reaper must still sweep jobs under any
    dead worker on every tick, not only the tick a worker transitions."""
    queue = seeded["queue"]
    project = seeded["project"]

    already_dead_worker = Worker(
        project_id=project.id,
        name="already-dead-worker",
        hostname="host-c",
        status=WorkerStatus.dead,
        queues=["*"],
        concurrency=5,
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    db_session.add(already_dead_worker)
    await db_session.flush()

    job = Job(
        queue_id=queue.id,
        type=JobType.immediate,
        status=JobStatus.running,
        handler="sleep",
        payload={"seconds": 5},
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        worker_id=already_dead_worker.id,
        lock_token=uuid.uuid4(),
    )
    db_session.add(job)
    await db_session.commit()

    stats = await reaper.reap_dead_workers(db_session, visibility_timeout_sec=30)
    await db_session.commit()

    assert stats["workers_reaped"] == 0  # not newly detected as stale
    assert stats["jobs_requeued"] == 1  # but its orphaned job is still swept

    await db_session.refresh(job)
    assert job.status == JobStatus.queued
    assert job.worker_id is None
