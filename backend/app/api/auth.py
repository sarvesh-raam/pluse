import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, TooManyRequestsError, UnauthorizedError
from app.core.ratelimit import login_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrgMembershipOut,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}|{body.email.lower()}"
    if login_limiter.is_blocked(limiter_key):
        raise TooManyRequestsError("Too many failed login attempts — try again in a few minutes")

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        login_limiter.record_failure(limiter_key)
        raise UnauthorizedError("Invalid email or password")
    login_limiter.reset(limiter_key)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    payload = decode_token(body.refresh_token, expected_type="refresh")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid token subject")

    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("User no longer exists")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    memberships = (
        await db.scalars(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).all()
    return MeResponse(
        user=UserOut.model_validate(user),
        memberships=[
            OrgMembershipOut(org_id=m.org_id, role=m.role.value) for m in memberships
        ],
    )
