"""Email sequences: templates, enrollment and the manual dispatch control.

The sending itself lives in :mod:`nexus.core.sequences`; this module is the HTTP
surface — write a sequence, put contacts into it, see where they are, and
(optionally) ask the dispatcher to run now instead of waiting for the poll loop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity
from nexus.core.db import get_session
from nexus.core.sequences import SEQUENCE_VARIABLES, dispatch_due, next_send_at_after, render
from nexus.database import (
    LIVE_SEQUENCE_STATUSES,
    Contact,
    EmailSequence,
    EmailSequenceEnrollment,
    EmailSequenceStep,
)

router = APIRouter(tags=["sequences"])

#: Enough steps for a real nurture campaign, few enough that a sequence stays
#: reviewable in one screen.
MAX_STEPS = 25


class StepInput(BaseModel):
    delay_days: int = Field(default=0, ge=0, le=365)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=50_000)


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[StepInput] = Field(default_factory=list, max_length=MAX_STEPS)


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    #: When present the step list is replaced wholesale, not merged.
    steps: list[StepInput] | None = Field(default=None, max_length=MAX_STEPS)


class EnrollRequest(BaseModel):
    contact_id: int = Field(ge=1)


class EnrollmentUpdate(BaseModel):
    #: ``active`` resumes a paused enrollment; ``cancelled`` ends it for good.
    status: Literal["active", "paused", "cancelled"]


class PreviewRequest(BaseModel):
    contact_id: int = Field(ge=1)


def _serialize_step(step: EmailSequenceStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "position": step.position,
        "delay_days": step.delay_days,
        "subject": step.subject,
        "body": step.body,
    }


def _serialize_sequence(sequence: EmailSequence, stats: dict[str, int] | None = None) -> dict[str, Any]:
    stats = stats or {}
    return {
        "id": sequence.id,
        "name": sequence.name,
        "description": sequence.description,
        "is_active": sequence.is_active,
        "steps": [_serialize_step(step) for step in sequence.steps],
        "step_count": len(sequence.steps),
        "active_enrollments": stats.get("active", 0) + stats.get("paused", 0),
        "completed_enrollments": stats.get("completed", 0),
        "failed_enrollments": stats.get("failed", 0),
        "emails_sent": stats.get("sent", 0),
        "created_at": sequence.created_at.isoformat() if sequence.created_at else None,
    }


def _serialize_enrollment(enrollment: EmailSequenceEnrollment) -> dict[str, Any]:
    contact = enrollment.contact
    return {
        "id": enrollment.id,
        "sequence_id": enrollment.sequence_id,
        "sequence_name": enrollment.sequence.name if enrollment.sequence else None,
        "contact_id": enrollment.contact_id,
        "contact_name": contact.display_name if contact else None,
        "contact_email": contact.email if contact else None,
        "status": enrollment.status,
        "current_step": enrollment.current_step,
        "next_send_at": enrollment.next_send_at.isoformat() if enrollment.next_send_at else None,
        "last_sent_at": enrollment.last_sent_at.isoformat() if enrollment.last_sent_at else None,
        "last_error": enrollment.last_error,
        "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
    }


async def _stats_by_sequence(session: AsyncSession) -> dict[int, dict[str, int]]:
    """Per-sequence enrollment counts and emails sent, in one grouped query."""
    rows = await session.execute(
        select(
            EmailSequenceEnrollment.sequence_id,
            EmailSequenceEnrollment.status,
            func.count(EmailSequenceEnrollment.id),
            func.coalesce(func.sum(EmailSequenceEnrollment.current_step), 0),
        ).group_by(EmailSequenceEnrollment.sequence_id, EmailSequenceEnrollment.status)
    )
    stats: dict[int, dict[str, int]] = {}
    for sequence_id, enrollment_status, count, sent in rows:
        bucket = stats.setdefault(sequence_id, {})
        bucket[enrollment_status] = int(count or 0)
        # current_step is the number of steps already sent for this enrollment,
        # so summing it per status gives the sequence's total sends.
        bucket["sent"] = bucket.get("sent", 0) + int(sent or 0)
    return stats


async def _get_sequence(session: AsyncSession, sequence_id: int) -> EmailSequence:
    sequence = await session.get(EmailSequence, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")
    return sequence


async def _replace_steps(session: AsyncSession, sequence: EmailSequence, steps: list[StepInput]) -> None:
    """Rewrite a sequence's steps from a fresh list.

    Written against the rows rather than the ``steps`` collection: a new or
    reloaded object has no collection loaded, and an async session refuses to
    load one on demand. The Core DELETE also runs before the inserts, so
    ``(sequence_id, position)`` never has two rows at once.
    """
    await session.execute(delete(EmailSequenceStep).where(EmailSequenceStep.sequence_id == sequence.id))
    for position, step in enumerate(steps):
        session.add(
            EmailSequenceStep(
                sequence_id=sequence.id,
                position=position,
                delay_days=step.delay_days,
                subject=step.subject.strip(),
                body=step.body,
            )
        )
    await session.flush()
    # Reload so the caller serialises the new steps, not whatever it held.
    await session.refresh(sequence)


@router.get("/sequences")
async def list_sequences(
    q: str = Query("", max_length=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    stmt = select(EmailSequence)
    if q:
        stmt = stmt.where(EmailSequence.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(EmailSequence.is_active.desc(), EmailSequence.name.asc())

    sequences = list((await session.execute(stmt)).scalars().unique().all())
    stats = await _stats_by_sequence(session)
    return {
        "items": [_serialize_sequence(sequence, stats.get(sequence.id)) for sequence in sequences],
        "variables": list(SEQUENCE_VARIABLES),
        "max_steps": MAX_STEPS,
    }


@router.post("/sequences", status_code=status.HTTP_201_CREATED)
async def create_sequence(
    body: SequenceCreate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    sequence = EmailSequence(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        created_by_id=current_user.id,
    )
    session.add(sequence)
    await session.flush()
    if body.steps:
        await _replace_steps(session, sequence, body.steps)
    else:
        # A fresh object has no collection loaded, and the serializer reads one.
        await session.refresh(sequence)
    await session.commit()
    return _serialize_sequence(sequence)


@router.get("/sequences/enrollments")
async def list_enrollments(
    contact_id: int | None = Query(None, ge=1),
    sequence_id: int | None = Query(None, ge=1),
    enrollment_status: str | None = Query(None, alias="status", max_length=20),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Enrollments, optionally for one contact or one sequence."""
    stmt = select(EmailSequenceEnrollment)
    if contact_id is not None:
        stmt = stmt.where(EmailSequenceEnrollment.contact_id == contact_id)
    if sequence_id is not None:
        stmt = stmt.where(EmailSequenceEnrollment.sequence_id == sequence_id)
    if enrollment_status:
        stmt = stmt.where(EmailSequenceEnrollment.status == enrollment_status)
    stmt = stmt.order_by(EmailSequenceEnrollment.created_at.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().unique().all())
    return {"items": [_serialize_enrollment(row) for row in rows]}


@router.patch("/sequences/enrollments/{enrollment_id}")
async def update_enrollment(
    enrollment_id: int,
    body: EnrollmentUpdate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    enrollment = await session.get(EmailSequenceEnrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    if body.status == "active":
        # Only a pause is resumable; a completed or cancelled enrollment is
        # history, and silently restarting it would surprise whoever cancelled it.
        if enrollment.status != "paused":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Enrollment is {enrollment.status} and cannot be resumed",
            )
        steps = sorted(enrollment.sequence.steps, key=lambda step: step.position)
        # Re-anchor the cadence to the moment of resuming, so a week on pause
        # does not fire every remaining step at once.
        enrollment.next_send_at = next_send_at_after(steps, enrollment.current_step, datetime.now(UTC))
        enrollment.status = "active"
    elif body.status == "paused":
        if enrollment.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only an active enrollment can be paused (this one is {enrollment.status})",
            )
        enrollment.status = "paused"
        enrollment.next_send_at = None
    else:
        enrollment.status = "cancelled"
        enrollment.next_send_at = None
        enrollment.last_error = None

    await session.commit()
    return _serialize_enrollment(enrollment)


@router.post("/sequences/dispatch")
async def dispatch(
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Send everything that is due right now.

    The app already polls; this exists so someone can prove a sequence works
    without waiting out a delay. It is not an admin-only power: anyone who can
    compose an email by hand can already send one now, this just does it for
    every step that has come due.
    """
    return await dispatch_due(session, limit=limit)


@router.get("/sequences/{sequence_id}")
async def get_sequence(
    sequence_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    sequence = await _get_sequence(session, sequence_id)
    stats = (await _stats_by_sequence(session)).get(sequence_id)
    return _serialize_sequence(sequence, stats)


@router.patch("/sequences/{sequence_id}")
async def update_sequence(
    sequence_id: int,
    body: SequenceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    sequence = await _get_sequence(session, sequence_id)
    if body.name is not None:
        sequence.name = body.name.strip()
    if body.description is not None:
        sequence.description = body.description.strip() or None
    if body.is_active is not None:
        sequence.is_active = body.is_active
    if body.steps is not None:
        await _replace_steps(session, sequence, body.steps)
    await session.commit()
    return _serialize_sequence(sequence)


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_200_OK)
async def delete_sequence(
    sequence_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Delete a sequence, its steps and every enrollment in it.

    The ORM cascade handles the children: they are eager-loaded on the fetched
    sequence, so a separate DELETE would race the cascade and warn that it
    matched no rows.
    """
    sequence = await _get_sequence(session, sequence_id)
    await session.delete(sequence)
    await session.commit()
    return {"deleted": True, "id": sequence_id}


@router.post("/sequences/{sequence_id}/enroll", status_code=status.HTTP_201_CREATED)
async def enroll(
    sequence_id: int,
    body: EnrollRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    sequence = await _get_sequence(session, sequence_id)
    if not sequence.steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one step before enrolling a contact",
        )

    contact = await session.get(Contact, body.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if contact.is_archived:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact is archived")
    if not (contact.email or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact has no email address",
        )

    existing = (
        await session.execute(
            select(EmailSequenceEnrollment).where(
                EmailSequenceEnrollment.sequence_id == sequence_id,
                EmailSequenceEnrollment.contact_id == contact.id,
                EmailSequenceEnrollment.status.in_(LIVE_SEQUENCE_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{contact.display_name or 'Contact'} is already in this sequence",
        )

    now = datetime.now(UTC)
    steps = sorted(sequence.steps, key=lambda step: step.position)
    enrollment = EmailSequenceEnrollment(
        sequence_id=sequence_id,
        contact_id=contact.id,
        status="active",
        current_step=0,
        next_send_at=next_send_at_after(steps, 0, now),
        created_by_id=current_user.id,
    )
    session.add(enrollment)

    await record_activity(
        session,
        action="sequence_enrolled",
        user_id=current_user.id,
        entity_type="contacts",
        entity_id=contact.id,
        description=f"Enrolled in sequence: {sequence.name}",
        metadata={"sequence_id": sequence_id, "sequence_name": sequence.name},
    )
    await session.commit()
    return _serialize_enrollment(enrollment)


@router.post("/sequences/{sequence_id}/preview")
async def preview(
    sequence_id: int,
    body: PreviewRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Render the steps against a real contact, so merge fields are checkable."""
    sequence = await _get_sequence(session, sequence_id)
    contact = await session.get(Contact, body.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return {
        "contact_id": contact.id,
        "contact_name": contact.display_name,
        "steps": [
            {
                "position": step.position,
                "delay_days": step.delay_days,
                "subject": render(step.subject, contact),
                "body": render(step.body, contact),
            }
            for step in sorted(sequence.steps, key=lambda step: step.position)
        ],
    }
