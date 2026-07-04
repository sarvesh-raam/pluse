import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.scoping import get_queue_scoped
from app.core.security import get_current_user
from app.db import get_db
from app.engine.dispatcher import replay_from_dlq
from app.models.dead_letter import DeadLetterEntry
from app.models.enums import MemberRole
from app.models.user import User
from app.schemas.dlq import DeadLetterEntryOut
from app.schemas.job import JobOut

router = APIRouter(prefix="/dlq", tags=["dlq"])


@router.get("", response_model=Page[DeadLetterEntryOut])
async def list_dlq(
    queue_id: uuid.UUID,
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[DeadLetterEntryOut]:
    await get_queue_scoped(db, queue_id, user, MemberRole.viewer)

    stmt = select(DeadLetterEntry).where(DeadLetterEntry.queue_id == queue_id)
    stmt = apply_sort(stmt, DeadLetterEntry, sort, order, default_field="failed_at")
    return await paginate(db, stmt, params, DeadLetterEntryOut)


@router.post("/{dlq_id}/replay", response_model=JobOut)
async def replay_dlq_entry(
    dlq_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(DeadLetterEntry, dlq_id)
    if entry is None:
        raise NotFoundError("Dead letter entry not found")
    if entry.replayed_at is not None:
        raise ConflictError("This dead letter entry has already been replayed")

    await get_queue_scoped(db, entry.queue_id, user, MemberRole.member)

    job = await replay_from_dlq(db, entry)
    await db.commit()
    await db.refresh(job)
    return job
