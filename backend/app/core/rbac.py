import uuid
from collections.abc import Callable

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole
from app.models.membership import OrganizationMember
from app.models.user import User

ROLE_ORDER: dict[MemberRole, int] = {
    MemberRole.viewer: 0,
    MemberRole.member: 1,
    MemberRole.admin: 2,
    MemberRole.owner: 3,
}


def role_at_least(role: MemberRole, minimum: MemberRole) -> bool:
    return ROLE_ORDER[role] >= ROLE_ORDER[minimum]


async def get_org_membership(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationMember:
    membership = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.user_id == user.id
        )
    )
    if membership is None:
        raise ForbiddenError("You are not a member of this organization")
    return membership


def require_role(minimum: MemberRole) -> Callable:
    async def dependency(
        membership: OrganizationMember = Depends(get_org_membership),
    ) -> OrganizationMember:
        if not role_at_least(membership.role, minimum):
            raise ForbiddenError(f"Requires role '{minimum.value}' or higher")
        return membership

    return dependency


async def ensure_role(
    db: AsyncSession, user: User, org_id: uuid.UUID, minimum: MemberRole
) -> OrganizationMember:
    """Non-dependency variant for use when org_id isn't a path/query param
    (e.g. it's embedded in a request body or resolved from another resource)."""
    membership = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.user_id == user.id
        )
    )
    if membership is None:
        raise ForbiddenError("You are not a member of this organization")
    if not role_at_least(membership.role, minimum):
        raise ForbiddenError(f"Requires role '{minimum.value}' or higher")
    return membership
