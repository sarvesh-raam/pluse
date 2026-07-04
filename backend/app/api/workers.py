import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import ensure_role
from app.core.scoping import get_project_or_404
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole
from app.models.user import User
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat
from app.schemas.worker import WorkerHeartbeatOut, WorkerOut

router = APIRouter(prefix="/workers", tags=["workers"])


async def _get_worker_scoped(db: AsyncSession, worker_id: uuid.UUID, user: User) -> Worker:
    worker = await db.get(Worker, worker_id)
    if worker is None:
        raise NotFoundError("Worker not found")
    project = await get_project_or_404(db, worker.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)
    return worker


@router.get("", response_model=Page[WorkerOut])
async def list_workers(
    project_id: uuid.UUID,
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[WorkerOut]:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    stmt = select(Worker).where(Worker.project_id == project_id)
    stmt = apply_sort(stmt, Worker, sort, order, default_field="registered_at")
    return await paginate(db, stmt, params, WorkerOut)


@router.get("/{worker_id}", response_model=WorkerOut)
async def get_worker(
    worker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Worker:
    return await _get_worker_scoped(db, worker_id, user)


@router.get("/{worker_id}/heartbeats", response_model=list[WorkerHeartbeatOut])
async def worker_heartbeats(
    worker_id: uuid.UUID,
    limit: int = 60,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkerHeartbeat]:
    await _get_worker_scoped(db, worker_id, user)

    rows = (
        await db.scalars(
            select(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_id == worker_id)
            .order_by(WorkerHeartbeat.ts.desc())
            .limit(limit)
        )
    ).all()
    return list(reversed(rows))
