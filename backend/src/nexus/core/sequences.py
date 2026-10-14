"""Email sequences: a short series of follow-ups, sent on a clock.

A sequence is a template — an ordered list of emails, each with a delay — and an
enrollment is one contact's progress through it. This module owns the two halves
that are easy to get wrong: rendering the merge fields, and deciding what to send
next.

Where this differs from the rest of the email code: a single send is a normal
request/response because someone is waiting for it, but a sequence is inherently
*not* driven by a request. Something has to wake up later, so the app runs one
polling loop that calls :func:`dispatch_due`. The loop is deliberately small:
progress lives in the database, so a restart, a redeploy or a second replica
changes nothing about what is owed.

Two honest caveats, both bounded:

* **A crash between the provider accepting a message and the enrollment being
  advanced re-sends that step.** At-least-once is the right trade for a follow-up
  email: a duplicate is visible and embarrassing, a silently dropped step is
  invisible. ``FOR UPDATE SKIP LOCKED`` stops two replicas claiming the same
  enrollment at the same instant, which is the failure that actually happens.
* **A provider refusal fails the enrollment rather than retrying.** Retrying with
  no backoff and no durable attempt counter would hammer the provider, and the
  realistic refusals (unverified domain, invalid recipient) do not fix
  themselves. The reason lands in ``last_error`` and on the sequence page.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.core.email import (
    EmailNotConfigured,
    EmailSendFailed,
    resolve_config,
    send_email,
)
from nexus.database import Contact, EmailSequence, EmailSequenceEnrollment

logger = logging.getLogger(__name__)

#: Merge fields an author may use, and what each one resolves to. Kept short and
#: contact-shaped on purpose: a variable that silently expands to nothing is
#: worse than one that never existed.
SEQUENCE_VARIABLES: tuple[str, ...] = (
    "first_name",
    "last_name",
    "full_name",
    "email",
    "job_title",
    "company",
    "city",
    "country",
)

#: ``{{ name }}``, case-insensitive and tolerant of inner spaces.
_TOKEN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)


def variables_for(contact: Contact) -> dict[str, str]:
    """The merge values for one contact. Missing fields render as empty.

    ``first_name``/``last_name`` fall back to splitting ``full_name``. Many CRM
    records carry only a full name, and a greeting that renders blank for most of
    the list is exactly the failure the visible-token rule exists to avoid.
    """
    name = (contact.display_name or "").strip()
    parts = name.split()
    company = (contact.company.name if contact.company else None) or contact.company_name
    return {
        "first_name": contact.first_name or (parts[0] if parts else ""),
        "last_name": contact.last_name or (parts[-1] if len(parts) > 1 else ""),
        "full_name": name,
        "email": contact.email or "",
        "job_title": contact.job_title or "",
        "company": company or "",
        "city": contact.city or "",
        "country": contact.country or "",
    }


def render(template: str | None, contact: Contact) -> str:
    """Expand merge fields against one contact.

    An unknown token is left exactly as written. Blanking it would turn a typo
    into an email with a hole in it and no way to notice; leaving it visible
    means the mistake is obvious in the sent message and in the preview.
    """
    values = variables_for(contact)
    return _TOKEN.sub(lambda match: values.get(match.group(1).lower(), match.group(0)), template or "")


def next_send_at_after(steps: list[Any], index: int, now: datetime) -> datetime | None:
    """When step ``index`` falls due, or ``None`` when the sequence is finished.

    The delay belongs to the step being scheduled, so scheduling step 2 waits for
    step 2's ``delay_days`` — not step 1's.
    """
    if index >= len(steps):
        return None
    return now + timedelta(days=max(0, int(steps[index].delay_days or 0)))


def _finish(enrollment: EmailSequenceEnrollment) -> None:
    enrollment.status = "completed"
    enrollment.next_send_at = None


async def dispatch_due(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Send every step that has come due, oldest first.

    Returns counts rather than raising: one broken enrollment must not stop the
    rest of the batch, and the caller (a poll loop or an admin button) has
    nothing useful to do with an exception but log it.
    """
    now = now or datetime.now(UTC)

    # Without a provider there is nothing to send. Checking once here keeps the
    # poll loop silent in a deployment that has not configured email at all.
    config = await resolve_config(session)
    if not config.configured:
        return {"sent": 0, "failed": 0, "completed": 0, "checked": 0, "skipped": "not_configured"}

    stmt = (
        select(EmailSequenceEnrollment)
        .join(EmailSequence, EmailSequence.id == EmailSequenceEnrollment.sequence_id)
        .where(
            EmailSequenceEnrollment.status == "active",
            EmailSequenceEnrollment.next_send_at.is_not(None),
            EmailSequenceEnrollment.next_send_at <= now,
            # Pausing the sequence parks everyone in it without editing each
            # enrollment.
            EmailSequence.is_active.is_(True),
        )
        .order_by(EmailSequenceEnrollment.next_send_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True, of=EmailSequenceEnrollment)
    )
    enrollments = list((await session.execute(stmt)).scalars().unique().all())

    sent = failed = completed = 0
    for enrollment in enrollments:
        sequence = enrollment.sequence
        if sequence is None:  # pragma: no cover - cascade deletes the enrollment first
            continue
        steps = sorted(sequence.steps, key=lambda step: step.position)

        if enrollment.current_step >= len(steps):
            _finish(enrollment)
            completed += 1
            continue

        step = steps[enrollment.current_step]
        contact = enrollment.contact
        if contact is None:  # pragma: no cover - cascade deletes the enrollment first
            continue

        if contact.is_archived:
            enrollment.status = "cancelled"
            enrollment.last_error = "Contact is archived"
            enrollment.next_send_at = None
            failed += 1
            continue

        recipient = (contact.email or "").strip()
        if not recipient:
            enrollment.status = "failed"
            enrollment.last_error = "Contact has no email address"
            enrollment.next_send_at = None
            failed += 1
            continue

        try:
            await send_email(
                session,
                # Attributed to whoever enrolled the contact, so the activity
                # trail names a person even though the clock sent it.
                user_id=enrollment.created_by_id or sequence.created_by_id,
                to=recipient,
                subject=render(step.subject, contact),
                text=render(step.body, contact),
                contact_id=contact.id,
            )
        except (EmailNotConfigured, EmailSendFailed) as exc:
            logger.warning("Sequence step failed for enrollment %s: %s", enrollment.id, exc)
            enrollment.status = "failed"
            enrollment.last_error = str(exc)[:500]
            enrollment.next_send_at = None
            failed += 1
            continue

        sent += 1
        enrollment.current_step += 1
        enrollment.last_sent_at = now
        enrollment.last_error = None
        upcoming = next_send_at_after(steps, enrollment.current_step, now)
        if upcoming is None:
            _finish(enrollment)
            completed += 1
        else:
            enrollment.next_send_at = upcoming

    await session.commit()
    return {"sent": sent, "failed": failed, "completed": completed, "checked": len(enrollments)}
