import asyncio

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemberRole
from tests.conftest import auth_headers, login, make_org_project_queue, registered_user


async def test_duplicate_idempotency_key_returns_same_job(
    client: AsyncClient, db_session: AsyncSession, registered_user: dict
):
    """§5.4: a duplicate POST /jobs with the same (queue_id, idempotency_key)
    must return the *existing* job with 200, not create a second row."""
    tokens = await login(client, registered_user["email"], registered_user["password"])
    headers = auth_headers(tokens["access_token"])

    seeded = await make_org_project_queue(db_session, registered_user["user"]["id"], MemberRole.owner)
    queue_id = str(seeded["queue"].id)

    body = {
        "queue_id": queue_id,
        "type": "immediate",
        "handler": "sleep",
        "payload": {"seconds": 1},
        "idempotency_key": "order-42",
    }

    first = await client.post("/api/v1/jobs", json=body, headers=headers)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/jobs", json=body, headers=headers)
    assert second.status_code == 200, second.text

    assert first.json()["id"] == second.json()["id"]


async def test_concurrent_duplicate_idempotency_key_still_yields_one_job(
    client: AsyncClient, db_session: AsyncSession, registered_user: dict
):
    """The race where two requests with the same idempotency_key hit the
    unique constraint at (almost) the same time must still converge on a
    single job (via the IntegrityError -> re-fetch fallback in create_job),
    not raise or create two rows."""
    tokens = await login(client, registered_user["email"], registered_user["password"])
    headers = auth_headers(tokens["access_token"])

    seeded = await make_org_project_queue(db_session, registered_user["user"]["id"], MemberRole.owner)
    queue_id = str(seeded["queue"].id)

    body = {
        "queue_id": queue_id,
        "type": "immediate",
        "handler": "sleep",
        "payload": {"seconds": 1},
        "idempotency_key": "concurrent-key",
    }

    responses = await asyncio.gather(
        *(client.post("/api/v1/jobs", json=body, headers=headers) for _ in range(5))
    )

    assert all(r.status_code in (200, 201) for r in responses)
    job_ids = {r.json()["id"] for r in responses}
    assert len(job_ids) == 1, f"expected exactly one distinct job id, got {job_ids}"

    created_count = sum(1 for r in responses if r.status_code == 201)
    assert created_count == 1


async def test_different_idempotency_keys_create_separate_jobs(
    client: AsyncClient, db_session: AsyncSession, registered_user: dict
):
    tokens = await login(client, registered_user["email"], registered_user["password"])
    headers = auth_headers(tokens["access_token"])

    seeded = await make_org_project_queue(db_session, registered_user["user"]["id"], MemberRole.owner)
    queue_id = str(seeded["queue"].id)

    first = await client.post(
        "/api/v1/jobs",
        json={
            "queue_id": queue_id, "type": "immediate", "handler": "sleep",
            "payload": {}, "idempotency_key": "key-a",
        },
        headers=headers,
    )
    second = await client.post(
        "/api/v1/jobs",
        json={
            "queue_id": queue_id, "type": "immediate", "handler": "sleep",
            "payload": {}, "idempotency_key": "key-b",
        },
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
