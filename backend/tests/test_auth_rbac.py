import uuid

from httpx import AsyncClient

from tests.conftest import auth_headers, login


async def test_unauthenticated_request_returns_401(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_register_login_me_round_trip(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    email = f"rbac-{suffix}@test.dev"
    password = "testpass123"

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "RBAC Tester"},
    )
    assert register.status_code == 201

    tokens = await login(client, email, password)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email


async def test_viewer_role_is_blocked_from_creating_a_queue(client: AsyncClient):
    """§7/§10 RBAC: viewer is read-only. A member with 'viewer' role must get
    403 attempting a mutating action like creating a queue (admin+ only)."""
    suffix = uuid.uuid4().hex[:8]

    owner_email, owner_password = f"owner-{suffix}@test.dev", "testpass123"
    viewer_email, viewer_password = f"viewer-{suffix}@test.dev", "testpass123"

    await client.post(
        "/api/v1/auth/register",
        json={"email": owner_email, "password": owner_password, "full_name": "Owner"},
    )
    await client.post(
        "/api/v1/auth/register",
        json={"email": viewer_email, "password": viewer_password, "full_name": "Viewer"},
    )

    owner_tokens = await login(client, owner_email, owner_password)
    owner_headers = auth_headers(owner_tokens["access_token"])

    org = await client.post(
        "/api/v1/orgs", json={"name": "RBAC Org", "slug": f"rbac-org-{suffix}"}, headers=owner_headers
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await client.post(
        "/api/v1/projects",
        json={"org_id": org_id, "name": "RBAC Project", "slug": f"rbac-project-{suffix}"},
        headers=owner_headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    invite = await client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": viewer_email, "role": "viewer"},
        headers=owner_headers,
    )
    assert invite.status_code == 201

    viewer_tokens = await login(client, viewer_email, viewer_password)
    viewer_headers = auth_headers(viewer_tokens["access_token"])

    resp = await client.post(
        "/api/v1/queues",
        json={"project_id": project_id, "name": "viewer-queue"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403

    # sanity check: the owner (admin+) *can* create it
    owner_resp = await client.post(
        "/api/v1/queues",
        json={"project_id": project_id, "name": "owner-queue"},
        headers=owner_headers,
    )
    assert owner_resp.status_code == 201


async def test_member_role_can_enqueue_but_not_configure_queues(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]

    owner_email, owner_password = f"owner2-{suffix}@test.dev", "testpass123"
    member_email, member_password = f"member-{suffix}@test.dev", "testpass123"

    await client.post(
        "/api/v1/auth/register",
        json={"email": owner_email, "password": owner_password, "full_name": "Owner"},
    )
    await client.post(
        "/api/v1/auth/register",
        json={"email": member_email, "password": member_password, "full_name": "Member"},
    )

    owner_tokens = await login(client, owner_email, owner_password)
    owner_headers = auth_headers(owner_tokens["access_token"])

    org = await client.post(
        "/api/v1/orgs", json={"name": "Member Org", "slug": f"member-org-{suffix}"}, headers=owner_headers
    )
    org_id = org.json()["id"]
    project = await client.post(
        "/api/v1/projects",
        json={"org_id": org_id, "name": "Member Project", "slug": f"member-project-{suffix}"},
        headers=owner_headers,
    )
    project_id = project.json()["id"]
    await client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": member_email, "role": "member"},
        headers=owner_headers,
    )
    queue = await client.post(
        "/api/v1/queues",
        json={"project_id": project_id, "name": "member-queue"},
        headers=owner_headers,
    )
    queue_id = queue.json()["id"]

    member_tokens = await login(client, member_email, member_password)
    member_headers = auth_headers(member_tokens["access_token"])

    # member CAN enqueue a job
    job_resp = await client.post(
        "/api/v1/jobs",
        json={"queue_id": queue_id, "type": "immediate", "handler": "sleep", "payload": {}},
        headers=member_headers,
    )
    assert job_resp.status_code == 201

    # member CANNOT reconfigure the queue (admin+ only)
    patch_resp = await client.patch(
        f"/api/v1/queues/{queue_id}", json={"concurrency_limit": 10}, headers=member_headers
    )
    assert patch_resp.status_code == 403
