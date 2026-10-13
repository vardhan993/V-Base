"""Operator CLI: bootstrap the first administrator and run database maintenance.

Usage::

    python -m nexus.commands.admin create-admin --email you@example.com --username you
    python -m nexus.commands.admin promote --email you@example.com
    python -m nexus.commands.admin cleanup-sessions
    python -m nexus.commands.admin stats
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import secrets
import sys

from nexus.core.config import settings

logger = logging.getLogger("vbase.admin")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _validated_email(raw: str) -> str:
    """Reject addresses the API would refuse, before an account is created.

    The API validates emails with pydantic's ``EmailStr``, which rejects
    reserved and special-use domains such as ``example.com`` and ``.test``. The
    CLI has to use the same rule, otherwise an operator can create an
    administrator that can never sign in.
    """
    from pydantic import EmailStr, TypeAdapter, ValidationError

    candidate = raw.strip().lower()
    try:
        return str(TypeAdapter(EmailStr).validate_python(candidate))
    except ValidationError as exc:
        reason = exc.errors()[0].get("msg", "invalid email address")
        raise SystemExit(f"Invalid email '{raw}': {reason}") from None


async def _create_admin(email: str, username: str, password: str | None, full_name: str | None) -> int:
    from sqlalchemy import func, select

    from nexus.core.db import session_scope
    from nexus.core.security import hash_password
    from nexus.database import User

    email = _validated_email(email)
    async with session_scope() as session:
        existing = (await session.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()

        if existing is not None:
            existing.is_superuser = True
            existing.is_active = True
            if password:
                existing.hashed_password = hash_password(password)
            print(f"Updated existing account {existing.email}: is_superuser=True")
            return 0

        plain = password or secrets.token_urlsafe(18)
        user = User(
            email=email,
            username=username.strip(),
            hashed_password=hash_password(plain),
            full_name=full_name or username.strip(),
            is_active=True,
            is_superuser=True,
            preferences={},
        )
        session.add(user)
        await session.flush()
        print("Created administrator account")
        print(f"  email:    {email}")
        print(f"  username: {username.strip()}")
        if password is None:
            # Printed once, on the operator's own terminal. Never logged.
            print(f"  password: {plain}")
            print("  Store this now: it cannot be recovered, only reset.")
        return 0


async def _promote(email: str, value: bool) -> int:
    from sqlalchemy import func, select

    from nexus.core.db import session_scope
    from nexus.database import User

    async with session_scope() as session:
        user = (
            await session.execute(select(User).where(func.lower(User.email) == email.lower().strip()))
        ).scalar_one_or_none()
        if user is None:
            print(f"No account found for {email}", file=sys.stderr)
            return 1
        user.is_superuser = value
        print(f"{user.email}: is_superuser={value}")
        return 0


async def _cleanup_sessions() -> int:
    from sqlalchemy import delete

    from nexus.core.db import session_scope
    from nexus.database import AuthSession

    async with session_scope() as session:
        result = await session.execute(
            delete(AuthSession).where((AuthSession.expires_at < _utcnow()) | (AuthSession.revoked_at.is_not(None)))
        )
        print(f"Deleted {result.rowcount or 0} expired or revoked session(s)")
        return 0


async def _stats() -> int:
    from sqlalchemy import func, select, text

    from nexus.core.db import session_scope
    from nexus.database import AuthSession, Company, Contact, ImportJob, User

    async with session_scope() as session:
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        size = (await session.execute(text("SELECT pg_database_size(current_database())"))).scalar()
        print(f"alembic revision : {revision}")
        print(f"database size    : {size:,} bytes")
        for label, model in (
            ("users", User),
            ("companies", Company),
            ("contacts", Contact),
            ("import jobs", ImportJob),
            ("active sessions", AuthSession),
        ):
            count = (await session.execute(select(func.count(model.id)))).scalar() or 0
            print(f"{label:<17}: {count}")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vbase-admin", description=f"{settings.app_name} operator tools")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="Create (or promote) an administrator account")
    create.add_argument("--email", required=True)
    create.add_argument("--username", required=True)
    create.add_argument("--password", default=None, help="Omit to generate a random password")
    create.add_argument("--full-name", dest="full_name", default=None)

    promote = sub.add_parser("promote", help="Grant the superuser role")
    promote.add_argument("--email", required=True)

    demote = sub.add_parser("demote", help="Remove the superuser role")
    demote.add_argument("--email", required=True)

    sub.add_parser("cleanup-sessions", help="Delete expired and revoked sessions")
    sub.add_parser("stats", help="Print row counts and the current schema revision")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "create-admin":
        return asyncio.run(_create_admin(args.email, args.username, args.password, args.full_name))
    if args.command == "promote":
        return asyncio.run(_promote(args.email, True))
    if args.command == "demote":
        return asyncio.run(_promote(args.email, False))
    if args.command == "cleanup-sessions":
        return asyncio.run(_cleanup_sessions())
    if args.command == "stats":
        return asyncio.run(_stats())
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
