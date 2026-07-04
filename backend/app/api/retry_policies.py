import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import ensure_role
from app.core.scoping import get_project_or_404
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole
from app.models.retry_policy import RetryPolicy
from app.models.user import User
from app.schemas.retry_policy import RetryPolicyCreate, RetryPolicyOut, RetryPolicyUpdate

router = APIRouter(prefix="/retry-policies", tags=["retry-policies"])


async def _get_policy_or_404(db: AsyncSession, policy_id: uuid.UUID) -> RetryPolicy:
    policy = await db.get(RetryPolicy, policy_id)
    if policy is None:
        raise NotFoundError("Retry policy not found")
    return policy


@router.get("", response_model=Page[RetryPolicyOut])
async def list_retry_policies(
    project_id: uuid.UUID,
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[RetryPolicyOut]:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)

    stmt = select(RetryPolicy).where(RetryPolicy.project_id == project_id)
    stmt = apply_sort(stmt, RetryPolicy, sort, order, default_field="name")
    return await paginate(db, stmt, params, RetryPolicyOut)


@router.post("", response_model=RetryPolicyOut, status_code=status.HTTP_201_CREATED)
async def create_retry_policy(
    body: RetryPolicyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetryPolicy:
    project = await get_project_or_404(db, body.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.admin)

    policy = RetryPolicy(**body.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/{policy_id}", response_model=RetryPolicyOut)
async def get_retry_policy(
    policy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetryPolicy:
    policy = await _get_policy_or_404(db, policy_id)
    project = await get_project_or_404(db, policy.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)
    return policy


@router.patch("/{policy_id}", response_model=RetryPolicyOut)
async def update_retry_policy(
    policy_id: uuid.UUID,
    body: RetryPolicyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RetryPolicy:
    policy = await _get_policy_or_404(db, policy_id)
    project = await get_project_or_404(db, policy.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.admin)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)
    return policy


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_retry_policy(
    policy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    policy = await _get_policy_or_404(db, policy_id)
    project = await get_project_or_404(db, policy.project_id)
    await ensure_role(db, user, project.org_id, MemberRole.admin)

    await db.delete(policy)
    await db.commit()
