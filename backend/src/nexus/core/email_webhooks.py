"""Delivery events from the email provider.

Sending tells us the provider accepted a message; it does not tell us the
message arrived, bounced or was read. Those arrive asynchronously on a webhook,
which is the only way to know a "sent" email was actually deliverable.

Resend signs its webhooks with Svix: the secret (``whsec_...``) is base64, and
the signature is an HMAC-SHA256 over ``<id>.<timestamp>.<body>``. Verification
is mandatory — without it, anyone who can reach the endpoint could mark their
own bounced mail as delivered.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import TERMINAL_EMAIL_STATUSES, EmailMessage

logger = logging.getLogger(__name__)

#: How far a signature timestamp may drift before the event is refused, which
#: bounds how long a captured request stays replayable.
TIMESTAMP_TOLERANCE = timedelta(minutes=5)

#: Provider event name -> the status stored on the message. Anything absent here
#: is still recorded in the event log but leaves the status untouched, so a new
#: provider event type cannot silently corrupt a known outcome.
EVENT_STATUSES: dict[str, str] = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.delivery_delayed": "delivery_delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
}

#: Providers whose webhook we know how to verify.
SUPPORTED_WEBHOOK_PROVIDERS = ("resend",)

#: Which payload shape to read, per provider.
_PROVIDER_EVENT_KEYS: dict[str, dict[str, str]] = {
    "resend": {
        "type": "type",
        "message_id": "data.email_id",
        "to": "data.to",
        "subject": "data.subject",
        "created_at": "created_at",
    }
}


class WebhookError(RuntimeError):
    """The event could not be accepted."""


def _decode_secret(secret: str) -> bytes:
    """Svix secrets are base64 after the ``whsec_`` prefix."""
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    try:
        return base64.b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise WebhookError("The webhook secret is not valid base64") from exc


def verify_signature(
    secret: str,
    *,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    body: bytes,
    now: datetime | None = None,
) -> None:
    """Raise :class:`WebhookError` unless the request is genuinely from Svix."""
    if not secret:
        raise WebhookError("No webhook secret is configured")
    if not svix_id or not svix_timestamp or not svix_signature:
        raise WebhookError("Missing signature headers")

    try:
        sent_at = datetime.fromtimestamp(int(svix_timestamp), tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise WebhookError("The signature timestamp is not a Unix time") from exc

    if abs((now or datetime.now(UTC)) - sent_at) > TIMESTAMP_TOLERANCE:
        raise WebhookError("The signature timestamp is outside the tolerance window")

    signed = b".".join([svix_id.encode(), svix_timestamp.encode(), body])
    expected = base64.b64encode(hmac.new(_decode_secret(secret), signed, hashlib.sha256).digest()).decode()

    # The header can carry several signatures ("v1,abc v1,def") during a secret
    # rotation; any match is acceptable.
    for candidate in svix_signature.split():
        scheme, _, value = candidate.partition(",")
        if scheme == "v1" and hmac.compare_digest(value, expected):
            return
    raise WebhookError("The signature does not match")


def _dig(payload: dict[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def parse_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a provider payload into the fields the database needs."""
    keys = _PROVIDER_EVENT_KEYS.get(provider)
    if keys is None:
        raise WebhookError(f"Unsupported webhook provider: {provider}")

    event_type = _dig(payload, keys["type"])
    if not isinstance(event_type, str) or not event_type:
        raise WebhookError("The event has no type")

    recipients = _dig(payload, keys["to"])
    if isinstance(recipients, str):
        recipients = [recipients]
    if not isinstance(recipients, list):
        recipients = []

    return {
        "type": event_type,
        "status": EVENT_STATUSES.get(event_type),
        "message_id": _dig(payload, keys["message_id"]),
        "recipients": [str(r) for r in recipients],
        "subject": _dig(payload, keys["subject"]),
        "occurred_at": _dig(payload, keys["created_at"]),
    }


async def apply_event(session: AsyncSession, provider: str, event: dict[str, Any]) -> EmailMessage | None:
    """Update the message an event refers to. Returns None when unmatched.

    Unmatched events are not an error: a message may have been sent before this
    feature existed, or from another system sharing the provider account.
    """
    message_id = event.get("message_id")
    if not message_id:
        return None

    row = (
        await session.execute(
            select(EmailMessage).where(
                EmailMessage.provider == provider,
                EmailMessage.provider_message_id == str(message_id),
            )
        )
    ).scalars().first()
    if row is None:
        return None

    recorded = {
        "type": event.get("type"),
        "status": event.get("status"),
        "at": event.get("occurred_at"),
        "recipients": event.get("recipients") or [],
    }
    # Reassign rather than append: SQLAlchemy does not track in-place mutation of
    # a JSONB list, so appending would never produce an UPDATE.
    row.events = [*(row.events or []), recorded]
    row.last_event_at = datetime.now(UTC)

    new_status = event.get("status")
    if new_status and row.status not in TERMINAL_EMAIL_STATUSES:
        row.status = new_status
    elif new_status in TERMINAL_EMAIL_STATUSES:
        # An open can arrive after a bounce; the bounce is the truth.
        row.status = new_status

    return row
