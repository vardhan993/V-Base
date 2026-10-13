from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import CustomField, CustomFieldValue

router = APIRouter(tags=["custom-fields"])

_ALLOWED_TYPES = {
    "text",
    "long_text",
    "number",
    "date",
    "url",
    "email",
    "phone",
    "boolean",
    "single_select",
    "multi_select",
}
_ALLOWED_ENTITIES = {"contact", "company"}


def _slug(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Field name must contain letters or numbers"
        )
    return key[:100]


def _serialize(f: CustomField) -> dict[str, Any]:
    return {
        "id": f.id,
        "entity_type": f.entity_type,
        "name": f.name,
        "key": f.key,
        "field_type": f.field_type,
        "is_required": f.is_required,
        "default_value": f.default_value,
        "options": f.options,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _validate_value(field: CustomField, value: Any) -> Any:
    """Validate a value against its field definition; raises 400 on mismatch."""
    if value is None:
        if field.is_required:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field.name}' is required")
        return None
    ft = field.field_type
    if ft == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field.name}' must be a number")
    elif ft == "boolean":
        if not isinstance(value, bool):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field.name}' must be true/false")
    elif ft in ("single_select",):
        if not isinstance(value, str) or (field.options and value not in field.options):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{field.name}' must be one of: {', '.join(field.options or [])}",
            )
    elif ft == "multi_select":
        if not isinstance(value, list) or (field.options and any(v not in field.options for v in value)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{field.name}' values must be within: {', '.join(field.options or [])}",
            )
    elif ft == "email":
        if not isinstance(value, str) or "@" not in value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field.name}' must be an email address"
            )
    elif ft in ("text", "long_text", "date", "url", "phone"):
        if not isinstance(value, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{field.name}' must be text")
    return value


@router.get("/custom-fields")
async def list_fields(
    entity_type: str | None = Query(None, pattern="^(contact|company)$"),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    stmt = select(CustomField).order_by(CustomField.entity_type, CustomField.name)
    if entity_type:
        stmt = stmt.where(CustomField.entity_type == entity_type)
    result = await session.execute(stmt)
    return [_serialize(f) for f in result.scalars().unique().all()]


@router.post("/custom-fields", status_code=status.HTTP_201_CREATED)
async def create_field(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    entity_type = (body.get("entity_type") or "").strip()
    name = (body.get("name") or "").strip()
    field_type = (body.get("field_type") or "").strip()
    if entity_type not in _ALLOWED_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="entity_type must be 'contact' or 'company'"
        )
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    if field_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"field_type must be one of: {', '.join(sorted(_ALLOWED_TYPES))}",
        )
    key = _slug(name)
    existing = (
        await session.execute(select(CustomField).where(CustomField.entity_type == entity_type, CustomField.key == key))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A field with this name already exists for this entity"
        )
    options = body.get("options")
    if field_type in ("single_select", "multi_select"):
        if not options or not isinstance(options, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Select fields require an 'options' list"
            )
    field = CustomField(
        entity_type=entity_type,
        name=name,
        key=key,
        field_type=field_type,
        is_required=bool(body.get("is_required", False)),
        default_value=body.get("default_value"),
        options=options,
        created_by_id=current_user.id,
    )
    session.add(field)
    await session.flush()
    await session.refresh(field)
    await session.commit()
    return _serialize(field)


@router.patch("/custom-fields/{field_id}", status_code=status.HTTP_200_OK)
async def update_field(
    field_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    field = await session.get(CustomField, field_id)
    if not field:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found")
    # Changing type/entity of a field that already holds values would silently
    # corrupt data, so it is rejected outright.
    if "field_type" in body and body["field_type"] != field.field_type:
        count = (
            await session.execute(
                select(CustomFieldValue.id).where(CustomFieldValue.custom_field_id == field.id).limit(1)
            )
        ).scalar_one_or_none()
        if count is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change field type while values exist; delete the field instead",
            )
        if body["field_type"] not in _ALLOWED_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid field_type")
        field.field_type = body["field_type"]
    if "name" in body and body["name"]:
        new_key = _slug(body["name"])
        if new_key != field.key:
            clash = (
                await session.execute(
                    select(CustomField).where(
                        CustomField.entity_type == field.entity_type,
                        CustomField.key == new_key,
                        CustomField.id != field.id,
                    )
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another field already uses this name")
            field.name, field.key = body["name"].strip(), new_key
    if "options" in body:
        field.options = body["options"]
    if "is_required" in body:
        field.is_required = bool(body["is_required"])
    await session.commit()
    await session.refresh(field)
    return _serialize(field)


@router.delete("/custom-fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field(
    field_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    field = await session.get(CustomField, field_id)
    if not field:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found")
    # Core DELETE runs immediately (not subject to unit-of-work ordering), so
    # child rows are guaranteed gone before the parent DELETE is flushed.
    from sqlalchemy import delete as _delete

    await session.execute(_delete(CustomFieldValue).where(CustomFieldValue.custom_field_id == field.id))
    await session.flush()
    await session.delete(field)
    await session.commit()


@router.get("/custom-fields/values/{entity_type}/{entity_id}")
async def get_values(
    entity_type: str,
    entity_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    if entity_type not in _ALLOWED_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="entity_type must be 'contact' or 'company'"
        )
    rows = (
        await session.execute(
            select(CustomFieldValue, CustomField)
            .join(CustomField, CustomField.id == CustomFieldValue.custom_field_id)
            .where(CustomFieldValue.entity_type == entity_type, CustomFieldValue.entity_id == entity_id)
        )
    ).all()
    return {f.key: v.value for v, f in rows}


@router.put("/custom-fields/values/{entity_type}/{entity_id}", status_code=status.HTTP_200_OK)
async def set_values(
    entity_type: str,
    entity_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    if entity_type not in _ALLOWED_ENTITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="entity_type must be 'contact' or 'company'"
        )
    incoming = body.get("values") or {}
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'values' must be an object")
    defs = (await session.execute(select(CustomField).where(CustomField.entity_type == entity_type))).scalars().all()
    by_key = {f.key: f for f in defs}
    for key in incoming:
        if key not in by_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown field: {key}")
    out: dict[str, Any] = {}
    for key, raw in incoming.items():
        clean = _validate_value(by_key[key], raw)
        row = (
            await session.execute(
                select(CustomFieldValue).where(
                    CustomFieldValue.entity_type == entity_type,
                    CustomFieldValue.entity_id == entity_id,
                    CustomFieldValue.custom_field_id == by_key[key].id,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.value = clean
        else:
            session.add(
                CustomFieldValue(
                    entity_type=entity_type, entity_id=entity_id, custom_field_id=by_key[key].id, value=clean
                )
            )
        out[key] = clean
    await session.commit()
    return {"entity_type": entity_type, "entity_id": entity_id, "values": out}
