"""Regression tests for the bugs fixed in the hardening pass: privilege
escalation, cross-tenant references, poison-pill recovery, cron catch-up,
scheduler leader election, DLQ/retry interplay, chaos kills, metrics."""

import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engine import reaper, scheduler
from app.models.dead_letter import DeadLetterEntry
from app.models.enums import ExecutionStatus, JobStatus, JobType, MemberRole, WorkerStatus
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.scheduled_job import ScheduledJob
from app.models.worker import Worker
from tests.conftest import auth_headers, login, make_org_project_queue


async def _user(client: AsyncClient, prefix: str) -> tuple[dict, dict]:
    """Register + log in a fresh user; returns (user json, auth headers)."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.dev"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": prefix},
    )
    assert resp.status_code == 201, resp.text
    tokens = await login(client, email, "testpass123")
    return resp.json(), auth_headers(tokens["access_token"])


def _worker(project_id, *, status=WorkerStatus.active, heartbeat_age_sec=0) -> Worker:
    return Worker(
        project_id=project_id,
        name=f"w-{uuid.uuid4().hex[:6]}",
        hostname="host",
        status=status,
        queues=["*"],
        concurrency=5,
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age_sec),
    )


def _job(queue_id, **kw) -> Job:
    defaults = dict(
        queue_id=queue_id, type=JobType.immediate, status=JobStatus.queued, handler="sleep",
        payload={}, run_at=datetime.now(timezone.utc), max_attempts=3,
    )
    defaults.update(kw)
    return Job(**defaults)


# --- RBAC -------------------------------------------------------------------


async def test_admin_cannot_grant_or_take_owner_role(client: AsyncClient, db_session: AsyncSession):
    owner, owner_h = await _user(client, "owner")
    admin, admin_h = await _user(client, "admin")
    ctx = await make_org_project_queue(db_session, uuid.UUID(owner["id"]))
    org_id = ctx["org"].id

    invite = await client.post(
        f"/api/v1/orgs/{org_id}/members", json={"email": admin["email"], "role": "admin"},
        headers=owner_h,
    )
    assert invite.status_code == 201
    admin_member_id = invite.json()["id"]

    # admin promoting themselves to owner
    resp = await client.patch(
        f"/api/v1/orgs/{org_id}/members/{admin_member_id}", json={"role": "owner"}, headers=admin_h
    )
    assert resp.status_code == 403

    # admin demoting / removing the owner
    members = (await client.get(f"/api/v1/orgs/{org_id}/members", headers=admin_h)).json()
    owner_member_id = next(m["id"] for m in members if m["role"] == "owner")
    resp = await client.patch(
        f"/api/v1/orgs/{org_id}/members/{owner_member_id}", json={"role": "viewer"}, headers=admin_h
    )
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/orgs/{org_id}/members/{owner_member_id}", headers=admin_h)
    assert resp.status_code == 403

    # admin inviting a new owner
    third, _ = await _user(client, "third")
    resp = await client.post(
        f"/api/v1/orgs/{org_id}/members", json={"email": third["email"], "role": "owner"},
        headers=admin_h,
    )
    assert resp.status_code == 403

    # the owner still can
    resp = await client.patch(
        f"/api/v1/orgs/{org_id}/members/{admin_member_id}", json={"role": "owner"}, headers=owner_h
    )
    assert resp.status_code == 200


# --- cross-tenant references -------------------------------------------------


async def test_queue_cannot_use_another_projects_retry_policy(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "tenant")
    mine = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    other = await make_org_project_queue(db_session, uuid.UUID(user["id"]))

    policy = await client.post(
        "/api/v1/retry-policies",
        json={"project_id": str(other["project"].id), "name": "p", "strategy": "fixed",
              "base_delay_sec": 1, "max_delay_sec": 1, "max_attempts": 2},
        headers=headers,
    )
    assert policy.status_code == 201

    resp = await client.patch(
        f"/api/v1/queues/{mine['queue'].id}", json={"retry_policy_id": policy.json()["id"]},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_depends_on_must_be_in_same_project(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "deps")
    mine = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    stranger, _ = await _user(client, "stranger")
    theirs = await make_org_project_queue(db_session, uuid.UUID(stranger["id"]))

    foreign = _job(theirs["queue"].id)
    db_session.add(foreign)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/jobs",
        json={"queue_id": str(mine["queue"].id), "type": "immediate", "handler": "sleep",
              "depends_on": [str(foreign.id)]},
        headers=headers,
    )
    assert resp.status_code == 422


# --- input validation ---------------------------------------------------------


async def test_patch_null_on_required_field_is_422_not_500(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "nulls")
    ctx = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    resp = await client.patch(f"/api/v1/queues/{ctx['queue'].id}", json={"name": None}, headers=headers)
    assert resp.status_code == 422


async def test_sort_by_non_column_is_ignored(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "sorter")
    ctx = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    for bad in ("queue", "__init__", "metadata", "executions"):
        resp = await client.get(
            "/api/v1/jobs", params={"project_id": str(ctx["project"].id), "sort": bad}, headers=headers
        )
        assert resp.status_code == 200, (bad, resp.text)


async def test_metrics_window_is_bounded(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "window")
    ctx = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    resp = await client.get(
        "/api/v1/metrics/throughput",
        params={"project_id": str(ctx["project"].id), "window": "999999d"}, headers=headers,
    )
    assert resp.status_code == 422


async def test_login_is_rate_limited_after_repeated_failures(client: AsyncClient):
    user, _ = await _user(client, "brute")
    for _ in range(10):
        resp = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong-pass"})
        assert resp.status_code == 401
    resp = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "testpass123"})
    assert resp.status_code == 429


# --- reaper: poison pills --------------------------------------------------------


async def test_reaper_charges_an_attempt_and_eventually_dead_letters(db_session: AsyncSession, seeded: dict):
    """A job that keeps killing its worker must not be requeued forever."""
    queue, project = seeded["queue"], seeded["project"]
    worker = _worker(project.id, heartbeat_age_sec=120)
    db_session.add(worker)
    await db_session.flush()

    job = _job(queue.id, status=JobStatus.running, worker_id=worker.id, lock_token=uuid.uuid4(),
               attempts=2, max_attempts=3)
    db_session.add(job)
    await db_session.flush()
    execution = JobExecution(job_id=job.id, worker_id=worker.id, attempt_number=3,
                             status=ExecutionStatus.running, started_at=datetime.now(timezone.utc))
    db_session.add(execution)
    await db_session.commit()

    stats = await reaper.reap_dead_workers(db_session, visibility_timeout_sec=30)
    await db_session.commit()

    assert stats["jobs_dead"] == 1 and stats["jobs_requeued"] == 0
    await db_session.refresh(job)
    await db_session.refresh(execution)
    assert job.status == JobStatus.dead and job.attempts == 3
    assert execution.status == ExecutionStatus.failed and execution.error_type == "WorkerLost"
    dlq = (await db_session.scalars(select(DeadLetterEntry).where(DeadLetterEntry.job_id == job.id))).all()
    assert len(dlq) == 1


async def test_reaper_does_not_charge_attempt_for_claimed_but_unstarted_job(db_session: AsyncSession, seeded: dict):
    queue, project = seeded["queue"], seeded["project"]
    worker = _worker(project.id, heartbeat_age_sec=120)
    db_session.add(worker)
    await db_session.flush()
    job = _job(queue.id, status=JobStatus.claimed, worker_id=worker.id, lock_token=uuid.uuid4(),
               attempts=2, max_attempts=3)
    db_session.add(job)
    await db_session.commit()

    await reaper.reap_dead_workers(db_session, visibility_timeout_sec=30)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.queued and job.attempts == 2


# --- scheduler -------------------------------------------------------------------


async def test_cron_after_downtime_spawns_one_job_not_a_burst(db_session: AsyncSession, seeded: dict):
    queue = seeded["queue"]
    sched = ScheduledJob(
        queue_id=queue.id, cron_expr="* * * * *", timezone="UTC", handler="sleep", payload={},
        next_run_at=datetime.now(timezone.utc) - timedelta(hours=3),  # 180 missed slots
    )
    db_session.add(sched)
    await db_session.commit()

    for _ in range(3):
        await scheduler.promote_cron_jobs(db_session)
        await db_session.commit()

    spawned = (await db_session.scalars(select(Job).where(Job.scheduled_job_id == sched.id))).all()
    assert len(spawned) == 1
    await db_session.refresh(sched)
    assert sched.next_run_at > datetime.now(timezone.utc)


async def test_broken_schedule_is_deactivated_without_failing_the_tick(db_session: AsyncSession, seeded: dict):
    queue = seeded["queue"]
    bad = ScheduledJob(queue_id=queue.id, cron_expr="* * * * *", timezone="Not/AZone", handler="sleep",
                       payload={}, next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    good = ScheduledJob(queue_id=queue.id, cron_expr="* * * * *", timezone="UTC", handler="sleep",
                        payload={}, next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    db_session.add_all([bad, good])
    await db_session.commit()

    assert await scheduler.promote_cron_jobs(db_session) == 1
    await db_session.commit()
    await db_session.refresh(bad)
    assert bad.is_active is False


async def test_only_one_scheduler_replica_ticks_at_a_time(engine: AsyncEngine, seeded: dict):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as leader, maker() as follower:
        await leader.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": scheduler.SCHEDULER_LOCK_KEY})
        # follower can't get the lock -> skips the tick entirely
        assert await scheduler.tick(follower) == {"promoted": 0, "spawned": 0, "deps_resolved": 0}
        await leader.rollback()


# --- retry / DLQ interplay ---------------------------------------------------------


async def test_retrying_dead_job_supersedes_its_dlq_entry(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "dlq")
    ctx = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    job = _job(ctx["queue"].id, status=JobStatus.dead, attempts=3)
    db_session.add(job)
    await db_session.flush()
    entry = DeadLetterEntry(job_id=job.id, queue_id=job.queue_id, payload={}, final_error="x", total_attempts=3)
    db_session.add(entry)
    await db_session.commit()

    assert (await client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)).status_code == 200
    # replaying the (now superseded) DLQ entry must not requeue the job again
    resp = await client.post(f"/api/v1/dlq/{entry.id}/replay", headers=headers)
    assert resp.status_code == 409


async def test_cancel_running_job_is_conflict(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _user(client, "cancel")
    ctx = await make_org_project_queue(db_session, uuid.UUID(user["id"]))
    job = _job(ctx["queue"].id, status=JobStatus.running)
    db_session.add(job)
    await db_session.commit()
    assert (await client.post(f"/api/v1/jobs/{job.id}/cancel", headers=headers)).status_code == 409


# --- chaos ---------------------------------------------------------------------------


async def test_chaos_kill_flags_a_live_worker_and_requires_admin(client: AsyncClient, db_session: AsyncSession):
    owner, owner_h = await _user(client, "chaos")
    ctx = await make_org_project_queue(db_session, uuid.UUID(owner["id"]))
    viewer, viewer_h = await _user(client, "chaosviewer")
    from app.models.membership import OrganizationMember

    db_session.add(OrganizationMember(org_id=ctx["org"].id, user_id=uuid.UUID(viewer["id"]),
                                      role=MemberRole.viewer))
    live = _worker(ctx["project"].id)
    stale = _worker(ctx["project"].id, heartbeat_age_sec=600)
    db_session.add_all([live, stale])
    await db_session.commit()

    body = {"project_id": str(ctx["project"].id)}
    assert (await client.post("/api/v1/chaos/kill", json=body, headers=viewer_h)).status_code == 403

    status = (await client.get("/api/v1/chaos/status", params=body, headers=owner_h)).json()
    assert status["live_workers"] == 1

    resp = await client.post("/api/v1/chaos/kill", json=body, headers=owner_h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["worker_id"] == str(live.id)  # never picks a stale worker
    assert resp.json()["mode"] == "signal"

    await db_session.refresh(live)
    assert live.chaos_kill_requested_at is not None
    # nothing left to kill
    assert (await client.post("/api/v1/chaos/kill", json=body, headers=owner_h)).status_code == 422


# --- observability ---------------------------------------------------------------------


async def test_metrics_and_probes(client: AsyncClient):
    await client.get("/healthz")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "pulse_http_requests_total" in resp.text
    assert 'route="/healthz"' in resp.text
    assert (await client.get("/dbcheck")).status_code == 404
