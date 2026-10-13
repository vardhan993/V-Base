from __future__ import annotations

import datetime
import logging
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.core.config import settings
from nexus.core.db import get_session
from nexus.core.security import hash_token
from nexus.database import AuthSession, User

logger = logging.getLogger(__name__)

#: How often ``last_seen_at`` is refreshed while a session is in use.
_LAST_SEEN_REFRESH = datetime.timedelta(minutes=15)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _as_aware(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.UTC)


async def get_current_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> AuthSession:
    """Resolve the caller's ``AuthSession`` row from the session cookie."""
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    stmt = select(AuthSession).where(AuthSession.token_hash == hash_token(session_token))
    auth_session = (await session.execute(stmt)).scalar_one_or_none()

    if auth_session is None or auth_session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    expires_at = _as_aware(auth_session.expires_at)
    if expires_at is not None and expires_at < _utcnow():
        await session.execute(update(AuthSession).where(AuthSession.id == auth_session.id).values(revoked_at=_utcnow()))
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    last_seen = _as_aware(auth_session.last_seen_at)
    if last_seen is None or _utcnow() - last_seen > _LAST_SEEN_REFRESH:
        auth_session.last_seen_at = _utcnow()
        await session.commit()

    request.state.session_id = auth_session.id
    return auth_session


async def get_current_user(
    auth_session: AuthSession = Depends(get_current_session),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive")
    return user


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """Server-side role gate. Never trust a role supplied by the client."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser role required")
    return current_user


def session_cookie_kwargs() -> dict:
    return {
        "key": settings.session_cookie_name,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "max_age": settings.session_max_age_seconds,
        "path": "/",
    }


def csrf_cookie_kwargs() -> dict:
    """CSRF token cookie.

    Readable by JavaScript on purpose: the SPA echoes it back in the
    ``X-CSRF-Token`` header (double-submit pattern). It is only useful when
    combined with the HttpOnly session cookie.
    """
    return {
        "key": "vbase_csrf",
        "httponly": False,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "max_age": settings.session_max_age_seconds,
        "path": "/",
    }


def attach_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    response.set_cookie(value=token, **session_cookie_kwargs())
    response.set_cookie(value=csrf_token, **csrf_cookie_kwargs())


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        "vbase_csrf",
        path="/",
        secure=settings.cookie_secure,
        samesite="lax",
    )


def client_ip(request: Request) -> str | None:
    """Best-effort client IP behind the hosting platform's proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client:
        return request.client.host[:45]
    return None
