import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnprocessableError
from app.core.notify import notify_jobs_available
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import ensure_role
from app.core.scoping import get_project_or_404, get_queue_scoped
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import ExecutionStatus, JobStatus, MemberRole
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.queue import Queue
from app.models.retry_policy import RetryPolicy
from app.models.user import User
from app.schemas.queue import QueueCreate, QueueOut, QueueStats, QueueUpdate

router = APIRouter(prefix="/queues", tags=["queues"])


async def _validate_retry_policy(
    db: AsyncSession, retry_policy_id: uuid.UUID | None, project_id: uuid.UUID
) -> None:
    """A queue may only reference a retry policy from its own project —
    otherwise anyone could attach (and read the settings of) another
    tenant's policy just by knowing its id."""
    if retry_policy_id is None:
        return
    policy_project_id = await db.scalar(
        select(RetryPolicy.project_id).where(RetryPolicy.id == retry_policy_id)
    )
    if policy_project_id != project_id:
        raise UnprocessableError("retry_policy_id does not refer to a retry policy in this project")


@router.get("", response_model=Page[QueueOut])
async def list_queues(
    project_id: uuid.UUID,
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[QueueOut]:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    stmt = select(Queue).where(Queue.project_id == project_id)
    stmt = apply_sort(stmt, Queue, sort, order)
    return await paginate(db, stmt, params, QueueOut)


@router.post("", response_model=QueueOut, status_code=status.HTTP_201_CREATED)
async def create_queue(
    body: QueueCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Queue:
    project = await get_project_or_404(db, body.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.admin)

    existing = await db.scalar(
        select(Queue).where(Queue.project_id == body.project_id, Queue.name == body.name)
    )
    if existing is not None:
        raise ConflictError("A queue with this name already exists in this project")
    await _validate_retry_policy(db, body.retry_policy_id, body.project_id)

    queue = Queue(**body.model_dump())
    db.add(queue)
    await db.commit()
    await db.refresh(queue)
    return queue


@router.get("/{queue_id}", response_model=QueueOut)
async def get_queue(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Queue:
    return await get_queue_scoped(db, queue_id, user, MemberRole.viewer)


@router.patch("/{queue_id}", response_model=QueueOut)
async def update_queue(
    queue_id: uuid.UUID,
    body: QueueUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Queue:
    queue = await get_queue_scoped(db, queue_id, user, MemberRole.admin)

    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] != queue.name:
        existing = await db.scalar(
            select(Queue).where(Queue.project_id == queue.project_id, Queue.name == updates["name"])
        )
        if existing is not None:
            raise ConflictError("A queue with this name already exists in this project")
    if "retry_policy_id" in updates:
        await _validate_retry_policy(db, updates["retry_policy_id"], queue.project_id)

    for field, value in updates.items():
        setattr(queue, field, value)

    await db.commit()
    await db.refresh(queue)
    return queue


@router.delete("/{queue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    queue = await get_queue_scoped(db, queue_id, user, MemberRole.admin)
    await db.delete(queue)
    await db.commit()


@router.post("/{queue_id}/pause", response_model=QueueOut)
async def pause_queue(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Queue:
    queue = await get_queue_scoped(db, queue_id, user, MemberRole.admin)
    queue.is_paused = True
    await db.commit()
    await db.refresh(queue)
    return queue


@router.post("/{queue_id}/resume", response_model=QueueOut)
async def resume_queue(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Queue:
    queue = await get_queue_scoped(db, queue_id, user, MemberRole.admin)
    queue.is_paused = False
    # jobs may have piled up while paused — wake workers now rather than on
    # their next poll tick
    await notify_jobs_available(db)
    await db.commit()
    await db.refresh(queue)
    return queue


@router.get("/{queue_id}/stats", response_model=QueueStats)
async def queue_stats(
    queue_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueStats:
    queue = await get_queue_scoped(db, queue_id, user, MemberRole.viewer)

    rows = (
        await db.execute(
            select(Job.status, func.count())
            .where(Job.queue_id == queue.id)
            .group_by(Job.status)
        )
    ).all()
    counts = {s.value: 0 for s in JobStatus}
    for job_status, count in rows:
        counts[job_status.value] = count

    duration_row = (
        await db.execute(
            select(
                func.avg(JobExecution.duration_ms),
                func.percentile_cont(0.95).within_group(JobExecution.duration_ms.asc()),
            )
            .join(Job, Job.id == JobExecution.job_id)
            .where(
                Job.queue_id == queue.id,
                JobExecution.status == ExecutionStatus.completed,
                JobExecution.duration_ms.is_not(None),
            )
        )
    ).one()
    avg_duration_ms, p95_duration_ms = duration_row

    terminal_total = counts["completed"] + counts["failed"] + counts["dead"]
    success_rate = counts["completed"] / terminal_total if terminal_total > 0 else None

    return QueueStats(
        queue_id=queue.id,
        scheduled=counts["scheduled"],
        queued=counts["queued"],
        claimed=counts["claimed"],
        running=counts["running"],
        completed=counts["completed"],
        failed=counts["failed"],
        retrying=counts["retrying"],
        dead=counts["dead"],
        cancelled=counts["cancelled"],
        success_rate=success_rate,
        avg_duration_ms=float(avg_duration_ms) if avg_duration_ms is not None else None,
        p95_duration_ms=float(p95_duration_ms) if p95_duration_ms is not None else None,
    )
