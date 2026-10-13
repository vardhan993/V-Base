from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import ActivityLog

router = APIRouter(tags=["activity"])


@router.get("/activity")
async def list_activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, max_length=100),
    entity_type: str | None = Query(None, max_length=100),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(ActivityLog).order_by(ActivityLog.created_at.desc())

    if action:
        base = base.where(ActivityLog.action.ilike(f"%{action}%"))
    if entity_type:
        base = base.where(ActivityLog.entity_type == entity_type)

    from sqlalchemy import func
    from sqlalchemy import select as select_fn

    total_stmt = select_fn(func.count()).select_from(ActivityLog)
    if action:
        total_stmt = total_stmt.where(ActivityLog.action.ilike(f"%{action}%"))
    if entity_type:
        total_stmt = total_stmt.where(ActivityLog.entity_type == entity_type)
    total = (await session.execute(total_stmt)).scalar_one()

    base = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(base)
    logs = list(result.scalars().unique().all())
    return {
        "items": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "description": a.description,
                "metadata": a._metadata,
                "ip_address": a.ip_address,
                "user_agent": a.user_agent,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
