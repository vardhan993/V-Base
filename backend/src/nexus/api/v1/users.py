from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.core.exceptions import NotFoundError
from nexus.database import User
from nexus.schemas.user import UserListResponse, UserResponse

router = APIRouter(tags=["users"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can list users")

    base = select(User).order_by(User.created_at.desc())
    if q:
        base = base.where(
            (User.email.ilike(f"%{q}%")) | (User.username.ilike(f"%{q}%")) | (User.full_name.ilike(f"%{q}%"))
        )
    base = base.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(base)
    users = list(result.scalars().all())

    total_stmt = select(User)
    if q:
        total_stmt = total_stmt.where(
            (User.email.ilike(f"%{q}%")) | (User.username.ilike(f"%{q}%")) | (User.full_name.ilike(f"%{q}%"))
        )
    total_result = await session.execute(total_stmt)
    total = len(list(total_result.scalars().all()))

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
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can view users")

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can update users")

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")

    for key, value in body.items():
        if key in {"email", "username", "full_name", "is_active", "is_superuser", "preferences"}:
            setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can deactivate users")

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
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superusers can restore users")

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    user.is_active = True
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)
