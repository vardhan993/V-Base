"""Public contact-form endpoint for the landing page.

Anyone browsing ``/#/`` can submit, so the endpoint is unauthenticated by
design — but it is not unprotected: Pydantic validates the shape, a honeypot
field plus a dedicated tight rate-limit bucket absorb bots, and every message
is stored before a best-effort forward to the team inbox.

The forward uses :func:`nexus.core.email.send_email`. That call *commits*, so
the row is saved first and the send is explicitly non-fatal: an unconfigured
provider must not lose a lead that is already on disk.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.core.config import settings
from nexus.core.db import get_session
from nexus.database import ContactMessage

try:  # The provider may not be set up; that is a runtime condition, not an import error.
    from nexus.core.email import EmailNotConfigured, EmailSendFailed, send_email
except RuntimeError:  # pragma: no cover - import-time config edge
    send_email = None  # type: ignore[assignment]

router = APIRouter(tags=["contact"])
logger = logging.getLogger("nexus.contact")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)

#: Tight cap for the public form — it is reachable without an account, so the
#: per-instance sliding window keeps one IP from flooding the mailbox or the
#: database. Configured via the rate-limit middleware's ``limits`` mapping.
CONTACT_RATE_LIMIT_PER_MINUTE = 5


class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    company: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=10, max_length=4000)
    #: Hidden field real users never fill; real submissions leave it empty.
    website: str = Field(default="", max_length=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Name is too short")
        return cleaned

    @field_validator("message")
    @classmethod
    def _reject_spammy_message(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 10:
            raise ValueError("Message is too short")
        if _URL_RE.search(cleaned):
            raise ValueError("Links are not allowed in the message")
        return cleaned


class ContactMessageResponse(BaseModel):
    id: int
    received: bool = True


def _looks_spammy(name: str, message: str) -> bool:
    """Cheap heuristic second layer beneath the honeypot and rate limit."""
    if _URL_RE.search(name):
        return True
    if re.search(r"[\u0400-\u04FF\u4e00-\u9fff]", message) and len(message) < 40:
        return True
    return False


@router.post("/contact", response_model=ContactMessageResponse, status_code=status.HTTP_201_CREATED)
async def submit_contact_message(
    body: ContactMessageCreate,
    session: AsyncSession = Depends(get_session),
) -> ContactMessageResponse:
    """Store a landing-page enquiry and forward it to the team inbox."""
    if _looks_spammy(body.name, body.message):
        # Deliberately indistinguishable from success: spammers learn nothing.
        logger.warning("Contact form heuristic spam from %s", body.email)
        return ContactMessageResponse(id=0)

    row = ContactMessage(
        name=body.name,
        email=str(body.email).lower(),
        company=(body.company or "").strip() or None,
        message=body.message,
        is_forwarded=False,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    forward_text = (
        f"New landing-page enquiry #{row.id}\n\n"
        f"Name: {body.name}\n Email: {body.email}\n"
        + (f"Company: {body.company}\n" if body.company else "")
        + f"\n{body.message}"
    )
    try:
        if send_email is None:
            raise EmailNotConfigured("Email provider not wired in this process")
        await send_email(
            session,
            user_id=None,
            to=settings.contact_form_inbox or settings.email_from,
            subject=f"[V-Base] Enquiry #{row.id} — {body.name}",
            text=forward_text,
            reply_to=str(body.email),
        )
        row.is_forwarded = True
        await session.commit()
    except (EmailNotConfigured, EmailSendFailed) as exc:
        # Stored is stored — the lead survives even if the pipe is down. Return
        # the normal response body with 202 so the client never sees an error.
        logger.error("Contact forward failed for message %s: %s", row.id, exc)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=ContactMessageResponse(id=row.id).model_dump(),
            headers={"X-Delivery": "pending"},
        )

    return ContactMessageResponse(id=row.id)
