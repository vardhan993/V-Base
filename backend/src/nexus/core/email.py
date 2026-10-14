"""Outbound email through a transactional provider.

V-Base stores contacts, not mailboxes. "Send an email" here means the API hands
one message to the provider and records the outcome in the activity trail —
there is no queue, no background worker and no retry, because the user is
waiting on the request.

Two providers are supported, and they are genuinely different shapes:

* **Resend** (``EMAIL_API_KEY``) — a JSON POST with an API key: the usual hosted
  transactional service, and the default.
* **Gmail** (``GOOGLE OAuth``) — sending from the team's own mailbox via the
  Gmail API. See :mod:`nexus.core.gmail`; it needs a refresh token, obtained
  through the connect flow rather than copied out of a dashboard.

Configuration precedence is *environment first, settings table second*: a
deployment sets its secrets in the environment, and an administrator can fill in
the rest from Settings without a redeploy. Credentials are write-only —
:func:`resolve_config` never exposes them to a response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.core import gmail as gmail_client
from nexus.core.audit import record_activity
from nexus.core.config import settings
from nexus.database import EmailMessage, SettingsRow

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "resend"

#: Providers whose request shape is a JSON body with ``from``/``to``/``subject``.
#: Gmail is not here: it takes a base64url RFC 2822 payload and an OAuth token.
_JSON_PROVIDERS: dict[str, str] = {
    "resend": "https://api.resend.com/emails",
}

SUPPORTED_PROVIDERS = (*_JSON_PROVIDERS, "gmail")

#: Settings-table keys an administrator may write through /settings/keys.
_SETTING_KEYS = (
    "email_provider",
    "email_api_key",
    "email_from",
    "email_from_name",
    "email_reply_to",
    "gmail_client_id",
    "gmail_client_secret",
    "gmail_refresh_token",
    "gmail_sender",
)


class EmailNotConfigured(RuntimeError):
    """Sending was attempted before the provider was set up."""


class EmailSendFailed(RuntimeError):
    """The provider accepted the call but rejected the message."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EmailConfig:
    provider: str
    from_email: str
    from_name: str
    reply_to: str | None
    resend_api_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    #: "environment", "settings" or "none" — never a credential itself.
    credential_source: str = "none"

    @property
    def sender(self) -> str:
        name = self.from_name or settings.app_name
        return f"{name} <{self.from_email}>" if self.from_email else name

    @property
    def missing(self) -> list[str]:
        """Setting names that still have to be supplied, in the order to fix them."""
        gaps: list[str] = []
        if self.provider == "gmail":
            if not self.gmail_client_id:
                gaps.append("gmail_client_id")
            if not self.gmail_client_secret:
                gaps.append("gmail_client_secret")
            if not self.gmail_refresh_token:
                gaps.append("gmail_refresh_token")
        elif self.provider in _JSON_PROVIDERS:
            if not self.resend_api_key:
                gaps.append("email_api_key")
        else:
            gaps.append("email_provider")
        if not self.from_email:
            gaps.append("email_from")
        return gaps

    @property
    def configured(self) -> bool:
        return not self.missing

    def gmail_credentials(self) -> gmail_client.GmailCredentials:
        return gmail_client.GmailCredentials(
            client_id=self.gmail_client_id,
            client_secret=self.gmail_client_secret,
            refresh_token=self.gmail_refresh_token,
            sender=self.from_email,
        )


async def _setting_overrides(session: AsyncSession) -> dict[str, str]:
    """Non-empty string rows from the settings table, keyed by name."""
    rows = (
        await session.execute(select(SettingsRow).where(SettingsRow.key.in_(_SETTING_KEYS)))
    ).scalars().all()
    overrides: dict[str, str] = {}
    for row in rows:
        value = row.value
        if isinstance(value, str) and value.strip():
            overrides[row.key] = value.strip()
    return overrides


async def resolve_config(session: AsyncSession) -> EmailConfig:
    """Effective email configuration for this process."""
    overrides = await _setting_overrides(session)

    def pick(setting_value: str, key: str) -> str:
        """Environment wins; the settings table fills anything left blank."""
        return (setting_value or "").strip() or overrides.get(key, "")

    provider = pick(settings.email_provider, "email_provider").lower() or DEFAULT_PROVIDER

    # A Gmail sender is configured by the connect flow, so it doubles as the
    # From address unless EMAIL_FROM says otherwise.
    from_email = pick(settings.email_from, "email_from") or (
        pick(settings.gmail_sender, "gmail_sender") if provider == "gmail" else ""
    )

    resend_api_key = pick(settings.email_api_key, "email_api_key")
    gmail_client_id = pick(settings.gmail_client_id, "gmail_client_id")
    gmail_client_secret = pick(settings.gmail_client_secret, "gmail_client_secret")
    gmail_refresh_token = pick(settings.gmail_refresh_token, "gmail_refresh_token")

    # Where the credential came from — reported, never the credential itself.
    has_env_credential = bool((settings.email_api_key or "").strip() or (settings.gmail_refresh_token or "").strip())
    if has_env_credential:
        source = "environment"
    elif resend_api_key or gmail_refresh_token:
        source = "settings"
    else:
        source = "none"

    return EmailConfig(
        provider=provider,
        from_email=from_email.strip(),
        from_name=pick(settings.email_from_name, "email_from_name"),
        reply_to=pick(settings.email_reply_to, "email_reply_to") or None,
        resend_api_key=resend_api_key,
        gmail_client_id=gmail_client_id,
        gmail_client_secret=gmail_client_secret,
        gmail_refresh_token=gmail_refresh_token,
        credential_source=source,
    )


def _provider_error(response: httpx.Response) -> str:
    """Best-effort human message from a provider error body."""
    try:
        body = response.json()
    except ValueError:
        return f"{response.status_code} {response.reason_phrase}".strip()
    if isinstance(body, dict):
        message = body.get("message")
        if not message and isinstance(body.get("error"), dict):
            message = body["error"].get("message")
        if message:
            return str(message)
    return f"{response.status_code} {response.reason_phrase}".strip()


async def send_message(
    config: EmailConfig,
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Hand one message to the provider. Raises on refusal."""
    if config.provider not in SUPPORTED_PROVIDERS:
        raise EmailNotConfigured(f"Unsupported email provider: {config.provider}")
    if config.missing:
        raise EmailNotConfigured(f"Email is not configured yet — still needed: {', '.join(config.missing)}")

    if config.provider == "gmail":
        try:
            return await gmail_client.send(
                config.gmail_credentials(),
                to=to,
                subject=subject,
                text=text,
                html=html,
                reply_to=reply_to,
            )
        except gmail_client.GmailError as exc:
            raise EmailSendFailed(str(exc), status_code=exc.status_code) from exc

    endpoint = _JSON_PROVIDERS[config.provider]
    payload: dict[str, Any] = {"from": config.sender, "to": [to], "subject": subject, "text": text}
    if html:
        payload["html"] = html
    effective_reply_to = reply_to or config.reply_to
    if effective_reply_to:
        payload["reply_to"] = effective_reply_to

    headers = {"Authorization": f"Bearer {config.resend_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=settings.email_timeout_seconds) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise EmailSendFailed(f"Could not reach {config.provider}: {exc}") from exc

    if response.status_code >= 400:
        raise EmailSendFailed(_provider_error(response), status_code=response.status_code)

    try:
        body = response.json()
    except ValueError:
        body = {}
    return {
        "id": body.get("id") if isinstance(body, dict) else None,
        "provider": config.provider,
        "status_code": response.status_code,
    }


async def send_email(
    session: AsyncSession,
    *,
    #: The person the send is attributed to, if any. A sequence sends on a clock,
    #: so it may have nobody to name.
    user_id: int | None,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
    contact_id: int | None = None,
) -> dict[str, Any]:
    """Send one message, record it and append it to the activity trail.

    Two records on purpose: the activity entry is the human-facing log line
    ("Emailed X: subject") and the ``email_messages`` row is the delivery record
    the provider's webhook later updates.
    """
    config = await resolve_config(session)
    result = await send_message(config, to=to, subject=subject, text=text, html=html, reply_to=reply_to)

    sent_at = datetime.now(UTC)
    message = EmailMessage(
        provider=config.provider,
        provider_message_id=(str(result["id"]) if result.get("id") else None),
        to_email=to,
        from_email=config.from_email or None,
        subject=subject[:500],
        body_preview=text[:280],
        status="sent",
        contact_id=contact_id,
        user_id=user_id,
        sent_at=sent_at,
        events=[],
    )
    session.add(message)

    await record_activity(
        session,
        action="email_sent",
        user_id=user_id,
        entity_type="contacts" if contact_id else None,
        entity_id=contact_id,
        description=f"Emailed {to}: {subject}",
        metadata={
            "to": to,
            "subject": subject,
            "provider": config.provider,
            "message_id": result.get("id"),
            "from": config.from_email,
            "preview": text[:280],
        },
    )
    await session.commit()

    return {
        "id": result.get("id"),
        "message_row_id": message.id,
        "provider": config.provider,
        "from": config.from_email,
        "to": to,
        "subject": subject,
        "status": message.status,
        "sent_at": sent_at.isoformat(),
    }


async def list_sent_messages(
    session: AsyncSession, *, contact_id: int | None = None, limit: int = 25
) -> list[dict[str, Any]]:
    """Recent sends, newest first, with whatever delivery status we know."""
    stmt = select(EmailMessage)
    if contact_id is not None:
        stmt = stmt.where(EmailMessage.contact_id == contact_id)
    stmt = stmt.order_by(EmailMessage.sent_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars().unique().all()
    return [
        {
            "id": row.id,
            "to": row.to_email,
            "subject": row.subject,
            "provider": row.provider,
            "message_id": row.provider_message_id,
            "from": row.from_email,
            "preview": row.body_preview,
            "status": row.status,
            "last_event_at": row.last_event_at.isoformat() if row.last_event_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "user_id": row.user_id,
        }
        for row in rows
    ]
