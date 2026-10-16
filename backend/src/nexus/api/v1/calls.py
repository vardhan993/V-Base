from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity
from nexus.core.db import get_session
from nexus.database import Call, Company, Contact

router = APIRouter(tags=["calls"])

_OUTCOMES = {"connected", "voicemail", "missed", "scheduled"}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _serialize(call: Call) -> dict[str, Any]:
    return {
        "id": call.id,
        "contact_id": call.contact_id,
        "company_id": call.company_id,
        "contact_name": call.contact.display_name if call.contact else None,
        "company_name": call.company.name if call.company else None,
        "direction": call.direction,
        "outcome": call.outcome,
        "duration_seconds": call.duration_seconds,
        "phone_number": call.phone_number,
        "notes": call.notes,
        "scheduled_followup_at": call.scheduled_followup_at.isoformat() if call.scheduled_followup_at else None,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


async def _load_call(session: AsyncSession, call_id: int) -> Call:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    return call


async def _verify_parent(session: AsyncSession, contact_id: int | None, company_id: int | None) -> None:
    if contact_id is None and company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A call needs contact_id or company_id",
        )
    if contact_id is not None:
        contact = await session.get(Contact, contact_id)
        if contact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if company_id is not None:
        company = await session.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")


@router.get("/calls")
async def list_calls(
    contact_id: int | None = Query(None),
    company_id: int | None = Query(None),
    outcome: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    if outcome is not None and outcome not in _OUTCOMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"outcome must be one of {sorted(_OUTCOMES)}")

    base = select(Call)
    if contact_id is not None:
        base = base.where(Call.contact_id == contact_id)
    if company_id is not None:
        base = base.where(Call.company_id == company_id)
    if outcome:
        base = base.where(Call.outcome == outcome)
    base = base.order_by(Call.created_at.desc())

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = list((await session.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().unique().all())

    outcome_counts = dict(
        (await session.execute(
            select(Call.outcome, func.count()).group_by(Call.outcome)
        )).all()
    )
    return {
        "items": [_serialize(c) for c in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "outcome_counts": outcome_counts,
    }


@router.post("/calls", status_code=status.HTTP_201_CREATED)
async def create_call(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    direction = str(body.get("direction") or "").strip().lower()
    outcome = str(body.get("outcome") or "").strip().lower()
    if direction not in ("inbound", "outbound"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="direction must be 'inbound' or 'outbound'")
    if outcome not in _OUTCOMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"outcome must be one of {sorted(_OUTCOMES)}")

    contact_id = body.get("contact_id")
    company_id = body.get("company_id")
    if isinstance(contact_id, str):
        contact_id = int(contact_id)
    if isinstance(company_id, str):
        company_id = int(company_id)
    await _verify_parent(session, contact_id, company_id)

    duration = body.get("duration_seconds")
    if duration is not None:
        duration = int(duration)
        if duration < 0 or duration > 24 * 3600:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duration_seconds out of range")

    call = Call(
        contact_id=contact_id,
        company_id=company_id,
        direction=direction,
        outcome=outcome,
        duration_seconds=duration,
        phone_number=(str(body["phone_number"]).strip()[:50] if body.get("phone_number") else None),
        notes=(str(body["notes"]) if body.get("notes") else None),
        created_by_id=current_user.id,
    )
    session.add(call)
    await record_activity(
        session,
        action="call_logged",
        user_id=current_user.id,
        entity_type="contacts" if contact_id else "companies",
        entity_id=contact_id or company_id,
        description=f"Logged {direction} call ({outcome})",
    )
    await session.commit()
    await session.refresh(call)
    return _serialize(call)


@router.patch("/calls/{call_id}")
async def update_call(
    call_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    call = await _load_call(session, call_id)

    if "outcome" in body:
        outcome = str(body["outcome"]).strip().lower()
        if outcome not in _OUTCOMES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"outcome must be one of {sorted(_OUTCOMES)}")
        call.outcome = outcome
    if "notes" in body:
        call.notes = str(body["notes"]) if body["notes"] else None
    if "duration_seconds" in body and body["duration_seconds"] is not None:
        duration = int(body["duration_seconds"])
        if duration < 0 or duration > 24 * 3600:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="duration_seconds out of range")
        call.duration_seconds = duration
    if "scheduled_followup_at" in body:
        raw = body["scheduled_followup_at"]
        if raw:
            call.scheduled_followup_at = datetime.datetime.fromisoformat(str(raw))
        else:
            call.scheduled_followup_at = None

    await session.commit()
    await session.refresh(call)
    return _serialize(call)


@router.delete("/calls/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_call(
    call_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    call = await _load_call(session, call_id)
    await session.delete(call)
    await session.commit()
