from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.core.exceptions import NotFoundError
from nexus.database import User
from nexus.schemas.user import UserListResponse, UserResponse, UserUpdate

router = APIRouter(tags=["users"])


async def _require_superuser_value(current_user: User) -> None:
    """Inline superuser gate with one canonical message."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can manage users")


def _count_where(q: str):
    if not q:
        return select(func.count()).select_from(User)
    pattern = f"%{q}%"
    return select(func.count()).select_from(User).where(
        (User.email.ilike(pattern)) | (User.username.ilike(pattern)) | (User.full_name.ilike(pattern))
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    await _require_superuser_value(current_user)

    base = select(User).order_by(User.created_at.desc())
    if q:
        pattern = f"%{q}%"
        base = base.where(
            (User.email.ilike(pattern)) | (User.username.ilike(pattern)) | (User.full_name.ilike(pattern))
        )
    base = base.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(base)
    users = list(result.scalars().all())

    total = (await session.execute(_count_where(q))).scalar_one()

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
):
    await _require_superuser_value(current_user)

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    # Typed schema replaces the previous raw "body: dict" mass assignment:
    # every field is validated, unknown keys are ignored, and client-supplied
    # truthy strings can no longer set is_active/is_superuser to non-boolean
    # values.
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    await _require_superuser_value(current_user)

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")

    # A superuser edits their own account at their own risk, but locking
    # themselves out of exactly the fields that grant admin access is a
    # footgun this endpoint must refuse.
    if user.id == current_user.id and (body.is_superuser is not None or body.is_active is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role or active status; ask another superuser",
        )
    if body.is_active is False and user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")

    changes = body.model_dump(exclude_unset=True, exclude_none=True)

    if "email" in changes and changes["email"] != user.email:
        taken = (
            await session.execute(select(User).where(User.email == str(changes["email"]).lower())).scalar_one_or_none()
        )
        if taken is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        user.email = str(changes["email"]).lower()

    if "username" in changes and changes["username"] != user.username:
        taken = (
            await session.execute(
                select(User).where(User.username == str(changes["username"]).strip())
            ).scalar_one_or_none()
        )
        if taken is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        user.username = str(changes["username"]).strip()

    if "full_name" in changes:
        user.full_name = changes["full_name"]
    for attr in ("is_active", "is_superuser"):
        value = changes.get(attr)
        if isinstance(value, bool):
            setattr(user, attr, value)
    if "preferences" in changes:
        user.preferences = changes["preferences"]

    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
):
    await _require_superuser_value(current_user)

    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.is_active = False
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/restore", response_model=UserResponse)
async def restore_user(
    user_id: int, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
):
    await _require_superuser_value(current_user)

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.is_active = True
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)
