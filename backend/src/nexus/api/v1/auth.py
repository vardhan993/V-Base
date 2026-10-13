from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import (
    attach_session_cookies,
    clear_session_cookie,
    client_ip,
    get_current_session,
    get_current_user,
)
from nexus.core.audit import record_activity
from nexus.core.db import get_session
from nexus.core.security import (
    generate_csrf_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from nexus.database import AuthSession, User
from nexus.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    SessionInfo,
    SignupRequest,
    TokenResponse,
)

router = APIRouter(tags=["auth"])

#: A freshly created account cannot be the 20th duplicate of an existing email.
_SESSION_TTL = datetime.timedelta(seconds=86400 * 7)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def _issue_session(
    session: AsyncSession,
    user: User,
    request: Request,
    response: Response,
) -> tuple[str, AuthSession]:
    """Create a session row and attach the session + CSRF cookies."""
    token = generate_token()
    csrf_token = generate_csrf_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=csrf_token,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        expires_at=_utcnow() + _SESSION_TTL,
        last_seen_at=_utcnow(),
    )
    session.add(auth_session)
    user.last_login_at = _utcnow()
    await session.flush()
    await session.commit()
    await session.refresh(auth_session)
    attach_session_cookies(response, token, csrf_token)
    return token, auth_session


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    email = body.email.lower().strip()
    username = body.username.strip()

    stmt = select(User).where((User.email == email) | (User.username == username))
    existing = (await session.execute(stmt)).scalars().first()
    if existing is not None:
        if existing.email == email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_active=True,
        is_superuser=False,
        preferences={},
    )
    session.add(user)
    await session.flush()

    await record_activity(
        session,
        action="signup",
        user_id=user.id,
        entity_type="users",
        entity_id=user.id,
        description="Account created",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    token, auth_session = await _issue_session(session, user, request, response)
    return TokenResponse(
        access_token=token,
        token_type="session",
        user_id=user.id,
        email=user.email,
        csrf_token=auth_session.csrf_token,
        expires_at=auth_session.expires_at,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    email = body.email.lower().strip()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    # Verify against a dummy hash when the user is missing so response timing
    # does not reveal whether an account exists.
    if user is None:
        verify_password(
            body.password,
            "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    await record_activity(
        session,
        action="login",
        user_id=user.id,
        entity_type="users",
        entity_id=user.id,
        description="User signed in",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    token, auth_session = await _issue_session(session, user, request, response)
    return TokenResponse(
        access_token=token,
        token_type="session",
        user_id=user.id,
        email=user.email,
        csrf_token=auth_session.csrf_token,
        expires_at=auth_session.expires_at,
    )


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_session),
):
    auth_session.revoked_at = _utcnow()
    await record_activity(
        session,
        action="logout",
        user_id=current_user.id,
        entity_type="users",
        entity_id=current_user.id,
        description="User signed out",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/auth/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_session),
):
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        preferences=current_user.preferences or {},
        session=SessionInfo(
            id=auth_session.id,
            created_at=auth_session.created_at,
            expires_at=auth_session.expires_at,
            last_seen_at=auth_session.last_seen_at,
        ),
    )


@router.get("/auth/sessions", response_model=list[SessionInfo])
async def list_sessions(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_session),
):
    stmt = (
        select(AuthSession)
        .where(
            AuthSession.user_id == current_user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > _utcnow(),
        )
        .order_by(AuthSession.created_at.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        SessionInfo(
            id=row.id,
            created_at=row.created_at,
            expires_at=row.expires_at,
            last_seen_at=row.last_seen_at,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            current=row.id == auth_session.id,
        )
        for row in rows
    ]


@router.delete("/auth/sessions", status_code=status.HTTP_200_OK)
async def revoke_other_sessions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_session),
):
    """Sign out everywhere else, keeping the calling session alive."""
    result = await session.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == current_user.id,
            AuthSession.id != auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )
    await record_activity(
        session,
        action="revoke_sessions",
        user_id=current_user.id,
        entity_type="users",
        entity_id=current_user.id,
        description=f"Revoked {result.rowcount} other session(s)",
        ip_address=client_ip(request),
    )
    await session.commit()
    return {"status": "ok", "revoked": result.rowcount or 0}


@router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_session),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters"
        )

    current_user.hashed_password = hash_password(body.new_password)
    # Rotating a password must invalidate every other session.
    revoked = await session.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == current_user.id,
            AuthSession.id != auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )
    await record_activity(
        session,
        action="change_password",
        user_id=current_user.id,
        entity_type="users",
        entity_id=current_user.id,
        description=f"Password changed; {revoked.rowcount} other session(s) revoked",
        ip_address=client_ip(request),
    )
    await session.commit()
    return {"status": "ok", "message": "Password changed successfully", "sessions_revoked": revoked.rowcount or 0}


@router.post("/auth/cleanup-sessions", status_code=status.HTTP_200_OK)
async def cleanup_sessions(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete expired/revoked session rows.

    Superuser-only: the scheduled maintenance script calls the same cleanup
    directly through ``nexus.core.db.session_scope``, so this route exists for
    operators who need to trigger it from the UI.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser role required")
    result = await session.execute(
        delete(AuthSession).where((AuthSession.expires_at < _utcnow()) | (AuthSession.revoked_at.is_not(None)))
    )
    await session.commit()
    return {"status": "ok", "deleted": result.rowcount or 0}
