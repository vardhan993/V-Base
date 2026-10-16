from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Call, Company, Contact, Lead, Note

router = APIRouter(tags=["notes"])


def _serialize(note: Note) -> dict[str, Any]:
    author = note.author
    author_name = (author.full_name or author.username or author.email) if author else None
    return {
        "id": note.id,
        "body": note.body,
        "pinned": note.pinned,
        "company_id": note.company_id,
        "contact_id": note.contact_id,
        "lead_id": note.lead_id,
        "author": author_name,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


async def _verify_parent(
    session: AsyncSession, contact_id: int | None, company_id: int | None, lead_id: int | None
) -> None:
    provided = sum(1 for v in (contact_id, company_id, lead_id) if v is not None)
    if provided != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of contact_id, company_id or lead_id is required",
        )
    if contact_id is not None and await session.get(Contact, contact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if company_id is not None and await session.get(Company, company_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    if lead_id is not None and await session.get(Lead, lead_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")


@router.get("/notes")
async def list_notes(
    contact_id: int | None = Query(None),
    company_id: int | None = Query(None),
    lead_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Note)
    if contact_id is not None:
        base = base.where(Note.contact_id == contact_id)
    if company_id is not None:
        base = base.where(Note.company_id == company_id)
    if lead_id is not None:
        base = base.where(Note.lead_id == lead_id)
    # Pinned notes float to the top, newest first within each group.
    base = base.order_by(Note.pinned.desc(), Note.created_at.desc())

    rows = list((await session.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    return {"items": [_serialize(n) for n in rows], "page": page, "page_size": page_size}


def _call_entry(call: Call) -> dict[str, Any]:
    return {
        "kind": "call",
        "id": call.id,
        "direction": call.direction,
        "outcome": call.outcome,
        "duration_seconds": call.duration_seconds,
        "notes": call.notes,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


def _note_entry(note: Note) -> dict[str, Any]:
    author = note.author
    author_name = (author.full_name or author.username or author.email) if author else None
    return {
        "kind": "note",
        "id": note.id,
        "body": note.body,
        "pinned": note.pinned,
        "author": author_name,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


@router.get("/timeline")
async def timeline(
    contact_id: int | None = Query(None),
    company_id: int | None = Query(None),
    lead_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Unified activity feed: notes + calls interleaved for one record."""
    provided = sum(1 for v in (contact_id, company_id, lead_id) if v is not None)
    if provided != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of contact_id, company_id or lead_id is required",
        )

    entries: list[dict[str, Any]] = []
    if contact_id is not None:
        calls = list((await session.execute(select(Call).where(Call.contact_id == contact_id).order_by(Call.created_at.desc()).limit(limit))).scalars())
        notes = list((await session.execute(select(Note).where(Note.contact_id == contact_id).order_by(Note.created_at.desc()).limit(limit))).scalars())
    elif company_id is not None:
        calls = list((await session.execute(select(Call).where(Call.company_id == company_id).order_by(Call.created_at.desc()).limit(limit))).scalars())
        notes = list((await session.execute(select(Note).where(Note.company_id == company_id).order_by(Note.created_at.desc()).limit(limit))).scalars())
    else:
        calls = list((await session.execute(select(Call).where(False).limit(0))).scalars())
        notes = list((await session.execute(select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at.desc()).limit(limit))).scalars())

    entries.extend(_call_entry(c) for c in calls)
    entries.extend(_note_entry(n) for n in notes)
    entries.sort(key=lambda e: e["created_at"] or "", reverse=True)
    return {"items": entries[:limit]}


@router.post("/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    text = str(body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="body is required")

    contact_id = body.get("contact_id")
    company_id = body.get("company_id")
    lead_id = body.get("lead_id")
    if isinstance(contact_id, str):
        contact_id = int(contact_id)
    if isinstance(company_id, str):
        company_id = int(company_id)
    if isinstance(lead_id, str):
        lead_id = int(lead_id)
    await _verify_parent(session, contact_id, company_id, lead_id)

    note = Note(
        body=text,
        contact_id=contact_id,
        company_id=company_id,
        lead_id=lead_id,
        pinned=bool(body.get("pinned", False)),
        created_by_id=current_user.id,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return _serialize(note)


@router.patch("/notes/{note_id}")
async def update_note(
    note_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    note = await session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if "body" in body:
        text = str(body["body"] or "").strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="body cannot be empty")
        note.body = text
    if "pinned" in body:
        note.pinned = bool(body["pinned"])
    await session.commit()
    await session.refresh(note)
    return _serialize(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    note = await session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    await session.delete(note)
    await session.commit()
