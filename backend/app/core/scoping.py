import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.rbac import ensure_role
from app.models.enums import MemberRole
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User


async def get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


async def get_queue_or_404(db: AsyncSession, queue_id: uuid.UUID) -> Queue:
    queue = await db.scalar(
        select(Queue).where(Queue.id == queue_id).options(selectinload(Queue.retry_policy))
    )
    if queue is None:
        raise NotFoundError("Queue not found")
    return queue


async def get_job_or_404(db: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    return job


async def get_queue_scoped(
    db: AsyncSession, queue_id: uuid.UUID, user: User, minimum: MemberRole
) -> Queue:
    """Load a queue and enforce the caller's role in its parent org."""
    queue = await get_queue_or_404(db, queue_id)
    project = await get_project_or_404(db, queue.project_id)
    await ensure_role(db, user, project.org_id, minimum)
    return queue


async def get_job_scoped(
    db: AsyncSession, job_id: uuid.UUID, user: User, minimum: MemberRole
) -> tuple[Job, Queue]:
    """Load a job + its queue and enforce the caller's role in the parent org."""
    job = await get_job_or_404(db, job_id)
    queue = await get_queue_or_404(db, job.queue_id)
    project = await get_project_or_404(db, queue.project_id)
    await ensure_role(db, user, project.org_id, minimum)
    return job, queue
