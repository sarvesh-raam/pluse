import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import Page, PaginationParams, apply_sort, paginate
from app.core.rbac import get_org_membership, require_role
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    MemberInvite,
    MemberOut,
    MemberRoleUpdate,
    OrgCreate,
    OrgOut,
)

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=Page[OrgOut])
async def list_orgs(
    params: PaginationParams = Depends(),
    sort: str | None = None,
    order: str = "desc",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[OrgOut]:
    stmt = (
        select(Organization)
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .where(OrganizationMember.user_id == user.id)
    )
    stmt = apply_sort(stmt, Organization, sort, order)
    return await paginate(db, stmt, params, OrgOut)


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    existing = await db.scalar(select(Organization).where(Organization.slug == body.slug))
    if existing is not None:
        raise ConflictError("An organization with this slug already exists")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    db.add(OrganizationMember(org_id=org.id, user_id=user.id, role=MemberRole.owner))
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(
    org_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> list[MemberOut]:
    rows = (
        await db.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.org_id == org_id)
            .options(selectinload(OrganizationMember.user))
        )
    ).all()
    return [
        MemberOut(
            id=m.id,
            org_id=m.org_id,
            user_id=m.user_id,
            role=m.role,
            email=m.user.email,
            full_name=m.user.full_name,
        )
        for m in rows
    ]


@router.post("/{org_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def invite_member(
    org_id: uuid.UUID,
    body: MemberInvite,
    membership: OrganizationMember = Depends(require_role(MemberRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    if body.role == MemberRole.owner:
        _ensure_can_manage_owner_role(membership)

    target_user = await db.scalar(select(User).where(User.email == body.email))
    if target_user is None:
        raise NotFoundError("No registered user with this email")

    existing = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.user_id == target_user.id
        )
    )
    if existing is not None:
        raise ConflictError("User is already a member of this organization")

    new_member = OrganizationMember(org_id=org_id, user_id=target_user.id, role=body.role)
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)
    return MemberOut(
        id=new_member.id,
        org_id=org_id,
        user_id=target_user.id,
        role=new_member.role,
        email=target_user.email,
        full_name=target_user.full_name,
    )


async def _count_owners(db: AsyncSession, org_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.org_id == org_id, OrganizationMember.role == MemberRole.owner)
    ) or 0


def _ensure_can_manage_owner_role(actor: OrganizationMember) -> None:
    """Admins manage members/viewers/admins, but only an owner may grant,
    change or revoke the owner role — otherwise any admin could promote
    themselves to owner and then demote or remove the real owners."""
    if actor.role != MemberRole.owner:
        raise ForbiddenError("Only an owner can grant, change or revoke the owner role")


@router.patch("/{org_id}/members/{member_id}", response_model=MemberOut)
async def update_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    body: MemberRoleUpdate,
    membership: OrganizationMember = Depends(require_role(MemberRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    target = await db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
        .options(selectinload(OrganizationMember.user))
    )
    if target is None:
        raise NotFoundError("Membership not found")

    if MemberRole.owner in (target.role, body.role):
        _ensure_can_manage_owner_role(membership)

    if target.role == MemberRole.owner and body.role != MemberRole.owner:
        if await _count_owners(db, org_id) <= 1:
            raise ForbiddenError("Cannot demote the last remaining owner")

    target.role = body.role
    await db.commit()
    await db.refresh(target)
    return MemberOut(
        id=target.id,
        org_id=target.org_id,
        user_id=target.user_id,
        role=target.role,
        email=target.user.email,
        full_name=target.user.full_name,
    )


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(MemberRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> None:
    target = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id, OrganizationMember.org_id == org_id
        )
    )
    if target is None:
        raise NotFoundError("Membership not found")

    if target.role == MemberRole.owner:
        _ensure_can_manage_owner_role(membership)
    if target.role == MemberRole.owner and await _count_owners(db, org_id) <= 1:
        raise ForbiddenError("Cannot remove the last remaining owner")

    await db.delete(target)
    await db.commit()
