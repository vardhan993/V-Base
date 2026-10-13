from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity
from nexus.core.db import get_session
from nexus.database import Company, Contact, FollowUpTask

router = APIRouter(tags=["tasks"])


def _serialize(task: FollowUpTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "contact_id": task.contact_id,
        "company_id": task.company_id,
        "contact_name": task.contact.display_name if task.contact else None,
        "company_name": task.company.name if task.company else None,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "done": task.done,
        "done_at": task.done_at.isoformat() if task.done_at else None,
        "overdue": bool(not task.done and task.due_at and task.due_at < datetime.now(task.due_at.tzinfo)),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/tasks")
async def list_tasks(
    done: bool | None = Query(None),
    overdue: bool | None = Query(None),
    contact_id: int | None = Query(None),
    company_id: int | None = Query(None),
    q: str = Query("", max_length=300),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(FollowUpTask)
    if done is not None:
        base = base.where(FollowUpTask.done.is_(done))
    if contact_id is not None:
        base = base.where(FollowUpTask.contact_id == contact_id)
    if company_id is not None:
        base = base.where(FollowUpTask.company_id == company_id)
    if q:
        base = base.where(FollowUpTask.title.ilike(f"%{q}%"))
    if overdue is True:
        base = base.where(
            FollowUpTask.done.is_(False),
            FollowUpTask.due_at.isnot(None),
            FollowUpTask.due_at < func.now(),
        )
    base = base.order_by(FollowUpTask.done.asc(), FollowUpTask.due_at.asc().nulls_last(), FollowUpTask.id.desc())

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = list((await session.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().unique().all())
    open_count = (
        await session.execute(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.done.is_(False)))
    ).scalar() or 0
    return {
        "items": [_serialize(t) for t in rows],
        "total": total,
        "open_count": open_count,
        "page": page,
        "page_size": page_size,
    }


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task title is required")
    contact_id = body.get("contact_id")
    company_id = body.get("company_id")
    if contact_id is not None and not await session.get(Contact, contact_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if company_id is not None and not await session.get(Company, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    due_at = body.get("due_at")
    if isinstance(due_at, str) and due_at:
        try:
            due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid due_at datetime") from exc
    else:
        due_at = None
    task = FollowUpTask(
        title=title[:300],
        notes=body.get("notes"),
        contact_id=contact_id,
        company_id=company_id,
        due_at=due_at,
        created_by_id=current_user.id,
    )
    session.add(task)
    await session.flush()
    await record_activity(
        session,
        action="task_created",
        user_id=current_user.id,
        entity_type="follow_up_tasks",
        entity_id=task.id,
        description=f"Task: {task.title}",
        metadata={"contact_id": contact_id, "company_id": company_id},
    )
    await session.commit()
    await session.refresh(task)
    return _serialize(task)


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    task = await session.get(FollowUpTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if "title" in body:
        title = (body["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task title cannot be blank")
        task.title = title[:300]
    if "notes" in body:
        task.notes = body["notes"]
    if "due_at" in body:
        raw = body["due_at"]
        if raw in (None, ""):
            task.due_at = None
        elif isinstance(raw, str):
            try:
                task.due_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid due_at datetime") from exc
    if "done" in body:
        from datetime import UTC

        task.done = bool(body["done"])
        task.done_at = datetime.now(UTC) if task.done else None
    await session.commit()
    await session.refresh(task)
    return _serialize(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    task = await session.get(FollowUpTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await session.delete(task)
    await session.commit()


@router.get("/tasks/summary")
async def tasks_summary(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    open_count = (
        await session.execute(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.done.is_(False)))
    ).scalar() or 0
    overdue_count = (
        await session.execute(
            select(func.count())
            .select_from(FollowUpTask)
            .where(FollowUpTask.done.is_(False), FollowUpTask.due_at.isnot(None), FollowUpTask.due_at < func.now())
        )
    ).scalar() or 0
    due_soon_count = (
        await session.execute(
            select(func.count())
            .select_from(FollowUpTask)
            .where(
                FollowUpTask.done.is_(False),
                FollowUpTask.due_at.isnot(None),
                FollowUpTask.due_at >= func.now(),
                FollowUpTask.due_at < func.now() + text("INTERVAL '7 days'"),
            )
        )
    ).scalar() or 0
    return {"open": open_count, "overdue": overdue_count, "due_soon": due_soon_count}
