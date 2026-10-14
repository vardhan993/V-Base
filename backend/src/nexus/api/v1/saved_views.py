from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import SavedView  # noqa: F401

def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if item is not None]

router = APIRouter(tags=["views"])

_ALLOWED_ENTITIES = {"companies", "contacts"}


class SavedViewOut(BaseModel):
    id: int
    name: str
    entity: str
    columns: list[str]
    sort: list[dict[str, Any]]
    filters: list[dict[str, Any]]
    created_at: str | None
    updated_at: str | None


def _serialize(v: SavedView) -> SavedViewOut:
    return SavedViewOut(
        id=v.id,
        name=v.name,
        entity=v.entity,
        columns=v.columns,
        sort=v.sort,
        filters=v.filters,
        created_at=v.created_at.isoformat() if v.created_at else None,
        updated_at=v.updated_at.isoformat() if v.updated_at else None,
    )


@router.get("/views", response_model=list[SavedViewOut])
async def list_views(
    entity: str | None = Query(None, pattern="^(companies|contacts)$"),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    stmt = select(SavedView).where(SavedView.created_by_id == current_user.id).order_by(SavedView.updated_at.desc())
    if entity:
        stmt = stmt.where(SavedView.entity == entity)
    result = await session.execute(stmt)
    return [_serialize(v) for v in result.scalars().unique().all()]


@router.post("/views", status_code=status.HTTP_201_CREATED, response_model=SavedViewOut)
async def create_view(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    name = (body.get("name") or "").strip()
    entity = (body.get("entity") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    if entity not in _ALLOWED_ENTITIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="entity must be 'companies' or 'contacts'")
    view = SavedView(
        name=name,
        entity=entity,columns=_normalize_list(body.get("columns")),        sort=_normalize_list(body.get("sort")),
        filters=_normalize_list(body.get("filters")),
        created_by_id=current_user.id,
    )
    session.add(view)
    await session.flush()
    await session.refresh(view)
    await session.commit()
    return _serialize(view)


@router.patch("/views/{view_id}", status_code=status.HTTP_200_OK, response_model=SavedViewOut)
async def update_view(
    view_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    view = await session.get(SavedView, view_id)
    if not view or view.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    if "name" in body and body["name"]:
        view.name = body["name"].strip()
    for attr in ("columns", "sort", "filters"):
        if attr in body:
            setattr(view, attr, _normalize_list(body[attr]) or [])
    await session.commit()
    await session.refresh(view)
    return _serialize(view)


@router.post("/views/{view_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=SavedViewOut)
async def duplicate_view(
    view_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    view = await session.get(SavedView, view_id)
    if not view or view.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    copy = SavedView(
        name=f"{view.name} (copy)",
        entity=view.entity,
        columns=_normalize_list(view.columns or []),
        sort=_normalize_list(view.sort or []),
        filters=_normalize_list(view.filters or []),
        created_by_id=current_user.id,
    )
    session.add(copy)
    await session.flush()
    await session.refresh(copy)
    await session.commit()
    return _serialize(copy)


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    view_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    view = await session.get(SavedView, view_id)
    if not view or view.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    await session.delete(view)
    await session.commit()
