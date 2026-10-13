from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nexus.core.context import request_info
from nexus.database import ActivityLog, AuditLog

logger = logging.getLogger(__name__)


def _context() -> tuple[str | None, str | None]:
    """Request IP and user-agent, when called inside a request."""
    info = request_info()
    if info is None:
        return None, None
    return info.ip_address, info.user_agent


async def record_activity(
    session: AsyncSession,
    *,
    action: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ActivityLog:
    """Append an activity entry. Caller owns the surrounding transaction."""
    ctx_ip, ctx_ua = _context()
    ip_address = ip_address or ctx_ip
    user_agent = user_agent or ctx_ua
    entry = ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        _metadata=metadata or {},
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    )
    session.add(entry)
    return entry


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: int,
    user_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append a before/after audit entry for a mutating operation."""
    ctx_ip, ctx_ua = _context()
    ip_address = ip_address or ctx_ip
    user_agent = user_agent or ctx_ua
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    )
    session.add(entry)
    return entry


def snapshot(model: Any, fields: list[str] | None = None) -> dict[str, Any]:
    """Serialisable field snapshot for audit ``before``/``after`` payloads.

    Only the named columns are captured, so audit rows never accidentally
    persist password hashes or other sensitive columns.
    """
    if fields is None:
        return {}
    out: dict[str, Any] = {}
    for field in fields:
        value = getattr(model, field, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        out[field] = value
    return out
