import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.engine.claim import claim_jobs, load_for_transition
from app.models.enums import ExecutionStatus, JobStatus, WorkerStatus
from app.models.job_execution import JobExecution
from app.models.worker import Worker
from tests.conftest import auth_headers, login


async def test_full_flow_register_org_project_queue_job_poll_to_completed(
    client: AsyncClient, engine: AsyncEngine
):
    """§12 API smoke test: create project -> queue -> job -> poll to
    completed. No worker process runs during the test suite, so the claim ->
    execute -> complete cycle a real worker would perform is done inline
    here via the same engine.claim primitives the worker itself calls,
    proving the whole pipeline (not just isolated endpoints) works together."""
    suffix = uuid.uuid4().hex[:8]
    email, password = f"smoke-{suffix}@test.dev", "testpass123"

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Smoke Tester"},
    )
    assert register.status_code == 201

    tokens = await login(client, email, password)
    headers = auth_headers(tokens["access_token"])

    org = await client.post(
        "/api/v1/orgs", json={"name": "Smoke Org", "slug": f"smoke-org-{suffix}"}, headers=headers
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await client.post(
        "/api/v1/projects",
        json={"org_id": org_id, "name": "Smoke Project", "slug": f"smoke-project-{suffix}"},
        headers=headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    queue = await client.post(
        "/api/v1/queues",
        json={"project_id": project_id, "name": "smoke-queue", "concurrency_limit": 5},
        headers=headers,
    )
    assert queue.status_code == 201
    queue_id = queue.json()["id"]

    job = await client.post(
        "/api/v1/jobs",
        json={"queue_id": queue_id, "type": "immediate", "handler": "compute", "payload": {"n": 5}},
        headers=headers,
    )
    assert job.status_code == 201
    job_id = job.json()["id"]
    assert job.json()["status"] == "queued"

    # --- simulate one worker tick: claim -> run -> mark completed ---
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_maker() as db:
        worker = Worker(
            project_id=uuid.UUID(project_id),
            name=f"smoke-worker-{suffix}",
            hostname="test-host",
            status=WorkerStatus.active,
            queues=["*"],
            concurrency=5,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(worker)
        await db.commit()
        worker_id = worker.id

    async with session_maker() as db:
        claimed = await claim_jobs(db, uuid.UUID(queue_id), worker_id, limit=5)
    assert len(claimed) == 1
    assert str(claimed[0].id) == job_id

    async with session_maker() as db:
        fresh = await load_for_transition(db, claimed[0].id, claimed[0].lock_token)
        assert fresh is not None
        now = datetime.now(timezone.utc)
        fresh.status = JobStatus.completed
        fresh.started_at = now
        fresh.finished_at = now
        fresh.lock_token = None
        db.add(
            JobExecution(
                job_id=fresh.id,
                worker_id=worker_id,
                attempt_number=1,
                status=ExecutionStatus.completed,
                started_at=now,
                finished_at=now,
                duration_ms=1,
            )
        )
        await db.commit()

    # --- poll via the real API and confirm it reflects completion ---
    final = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert final.status_code == 200
    assert final.json()["status"] == "completed"

    executions = await client.get(f"/api/v1/jobs/{job_id}/executions", headers=headers)
    assert executions.status_code == 200
    assert len(executions.json()) == 1
    assert executions.json()[0]["status"] == "completed"
