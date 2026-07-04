import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import ensure_role, require_role
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Page[ProjectOut])
async def list_projects(
    org_id: uuid.UUID,
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    _membership=Depends(require_role(MemberRole.viewer)),
    db: AsyncSession = Depends(get_db),
) -> Page[ProjectOut]:
    stmt = select(Project).where(Project.org_id == org_id)
    stmt = apply_sort(stmt, Project, sort, order)
    return await paginate(db, stmt, params, ProjectOut)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    await ensure_role(db, user, body.org_id, MemberRole.admin)

    existing = await db.scalar(
        select(Project).where(Project.org_id == body.org_id, Project.slug == body.slug)
    )
    if existing is not None:
        raise ConflictError("A project with this slug already exists in this organization")

    project = Project(org_id=body.org_id, name=body.name, slug=body.slug)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")

    await ensure_role(db, user, project.org_id, MemberRole.viewer)
    return project
