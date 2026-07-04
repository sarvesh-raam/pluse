import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.engine.claim import claim_jobs
from app.models.enums import JobStatus, JobType, WorkerStatus
from app.models.job import Job
from app.models.worker import Worker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _make_worker(session_maker, project_id) -> uuid.UUID:
    """jobs.worker_id carries a real FK to workers(id) — claim_jobs would
    fail its own FK constraint against a made-up id, so tests need an actual
    Worker row, same as a real worker process registers one on startup."""
    async with session_maker() as db:
        worker = Worker(
            project_id=project_id,
            name=f"test-worker-{uuid.uuid4().hex[:8]}",
            hostname="test-host",
            status=WorkerStatus.active,
            queues=["*"],
            concurrency=5,
            last_heartbeat_at=utcnow(),
        )
        db.add(worker)
        await db.commit()
        return worker.id


async def test_two_concurrent_claims_on_one_job_only_one_wins(engine: AsyncEngine, seeded: dict):
    """§5.1: FOR UPDATE SKIP LOCKED must guarantee exactly one claimant for a
    single queued job, even when two workers race for it at the same instant."""
    queue = seeded["queue"]
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_maker() as setup_db:
        job = Job(
            queue_id=queue.id,
            type=JobType.immediate,
            status=JobStatus.queued,
            handler="sleep",
            payload={"seconds": 0},
            run_at=utcnow(),
            max_attempts=3,
        )
        setup_db.add(job)
        await setup_db.commit()
        job_id = job.id

    worker_a = await _make_worker(session_maker, seeded["project"].id)
    worker_b = await _make_worker(session_maker, seeded["project"].id)

    async def claim_as(worker_id: uuid.UUID) -> list[Job]:
        async with session_maker() as db:
            return await claim_jobs(db, queue.id, worker_id, limit=5)

    results = await asyncio.gather(claim_as(worker_a), claim_as(worker_b))

    total_claimed = sum(len(r) for r in results)
    assert total_claimed == 1, f"expected exactly one winner, got {total_claimed}"

    async with session_maker() as verify_db:
        job = await verify_db.get(Job, job_id)
        assert job.status == JobStatus.claimed
        assert job.worker_id in (worker_a, worker_b)
        assert job.lock_token is not None


async def test_claim_respects_concurrency_limit_under_contention(engine: AsyncEngine, seeded: dict):
    """Beyond not double-claiming, the claim query must never let the
    aggregate claimed+running count for a queue exceed concurrency_limit,
    even when multiple workers claim concurrently."""
    queue = seeded["queue"]
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_maker() as setup_db:
        q = await setup_db.get(type(queue), queue.id)
        q.concurrency_limit = 2
        for _ in range(10):
            setup_db.add(
                Job(
                    queue_id=queue.id,
                    type=JobType.immediate,
                    status=JobStatus.queued,
                    handler="sleep",
                    payload={"seconds": 0},
                    run_at=utcnow() - timedelta(seconds=1),
                    max_attempts=3,
                )
            )
        await setup_db.commit()

    async def claim_as(worker_id: uuid.UUID) -> list[Job]:
        async with session_maker() as db:
            return await claim_jobs(db, queue.id, worker_id, limit=10)

    worker_ids = [await _make_worker(session_maker, seeded["project"].id) for _ in range(5)]
    results = await asyncio.gather(*(claim_as(w) for w in worker_ids))
    total_claimed = sum(len(r) for r in results)

    assert total_claimed == 2, f"expected exactly concurrency_limit=2 claimed, got {total_claimed}"

    async with session_maker() as verify_db:
        remaining_queued = (
            await verify_db.scalars(
                select(Job).where(Job.queue_id == queue.id, Job.status == JobStatus.queued)
            )
        ).all()
        assert len(remaining_queued) == 8
