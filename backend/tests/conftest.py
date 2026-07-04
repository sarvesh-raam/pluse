import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (populates Base.metadata with every table)
from app.db import Base, get_db
from app.main import app as fastapi_app
from app.models.enums import MemberRole
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.project import Project
from app.models.queue import Queue

ADMIN_DSN = "postgresql://pulse:pulse@localhost:5432/postgres"
TEST_DB_NAME = "pulse_test"
TEST_DATABASE_URL = f"postgresql+asyncpg://pulse:pulse@localhost:5432/{TEST_DB_NAME}"


async def _ensure_test_database() -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_test_database()
    eng = create_async_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    # Tests commit deliberately (to exercise real transactions, e.g. for
    # claim-atomicity across separate connections), so rollback alone isn't
    # enough for isolation — truncate everything between tests instead.
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> dict:
    """A bare org/project/queue for engine-level tests that talk to the DB
    directly rather than through the API."""
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name="Test Org", slug=f"test-org-{suffix}")
    db_session.add(org)
    await db_session.flush()

    project = Project(org_id=org.id, name="Test Project", slug=f"test-project-{suffix}")
    db_session.add(project)
    await db_session.flush()

    queue = Queue(project_id=project.id, name=f"queue-{suffix}", concurrency_limit=5)
    db_session.add(queue)
    await db_session.flush()
    await db_session.commit()

    return {"org": org, "project": project, "queue": queue}


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Registers a fresh user via the real API and returns their credentials
    plus a helper to log in."""
    suffix = uuid.uuid4().hex[:8]
    email = f"user-{suffix}@test.dev"
    password = "testpass123"
    full_name = "Test User"

    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert resp.status_code == 201, resp.text
    return {"email": email, "password": password, "full_name": full_name, "user": resp.json()}


async def login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def make_org_project_queue(
    db_session: AsyncSession, user_id: uuid.UUID, role: MemberRole = MemberRole.owner
) -> dict:
    """Like `seeded`, but also attaches the given user as a member with the
    given role — used by RBAC tests that need a specific role."""
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name="Test Org", slug=f"test-org-{suffix}")
    db_session.add(org)
    await db_session.flush()

    db_session.add(OrganizationMember(org_id=org.id, user_id=user_id, role=role))

    project = Project(org_id=org.id, name="Test Project", slug=f"test-project-{suffix}")
    db_session.add(project)
    await db_session.flush()

    queue = Queue(project_id=project.id, name=f"queue-{suffix}", concurrency_limit=5)
    db_session.add(queue)
    await db_session.flush()
    await db_session.commit()

    return {"org": org, "project": project, "queue": queue}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
