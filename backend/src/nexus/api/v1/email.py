"""Email endpoints: configuration status, sending, and the Gmail connect flow.

Sending is a synchronous request/response: the provider call happens inside the
request so a failure surfaces immediately instead of disappearing into a queue.
Every accepted message is appended to the activity trail, which is also where
:func:`list_sent_messages` reads the history from — no extra table, and the
sends show up in the global Activity feed alongside everything else.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user, require_superuser
from nexus.core import email_webhooks as webhooks
from nexus.core import gmail as gmail_client
from nexus.core.config import settings
from nexus.core.db import get_session
from nexus.core.email import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    EmailNotConfigured,
    EmailSendFailed,
    list_sent_messages,
    resolve_config,
    send_email,
)
from nexus.core.email_webhooks import SUPPORTED_WEBHOOK_PROVIDERS
from nexus.database import Contact, SettingsRow

logger = logging.getLogger(__name__)
router = APIRouter(tags=["email"])

#: Environment variable names an operator can set instead of using the UI.
ENV_VARS = ("EMAIL_PROVIDER", "EMAIL_API_KEY", "EMAIL_FROM", "EMAIL_REPLY_TO")
#: Extra names that only apply to the Gmail provider.
GMAIL_ENV_VARS = ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "GMAIL_SENDER")


class SendEmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=50_000)
    html: str | None = Field(default=None, max_length=200_000)
    reply_to: EmailStr | None = None
    #: Link the send to a contact so it appears on that record's timeline.
    contact_id: int | None = None


@router.get("/email/status")
async def email_status(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Whether sending is possible, and what is still missing if not.

    Credentials are never returned — only whether they were found and whether
    they came from the environment or the settings table.
    """
    config = await resolve_config(session)
    return {
        "configured": config.configured,
        "provider": config.provider,
        "supported_providers": list(SUPPORTED_PROVIDERS),
        "from_email": config.from_email or None,
        "from_name": config.from_name or None,
        "reply_to": config.reply_to,
        "credential_source": config.credential_source,
        "missing": config.missing,
        "default_provider": DEFAULT_PROVIDER,
        "env_vars": list(ENV_VARS),
        "gmail_env_vars": list(GMAIL_ENV_VARS),
        "setting_keys": [
            "email_provider",
            "email_api_key",
            "email_from",
            "email_from_name",
            "email_reply_to",
            "gmail_client_id",
            "gmail_client_secret",
            "gmail_refresh_token",
            "gmail_sender",
        ],
        # Only meaningful while Gmail is selected.
        "gmail_connect_url": "/api/v1/email/gmail/authorize" if config.provider == "gmail" else None,
        "gmail_connected": bool(config.gmail_refresh_token),
        # Delivery tracking needs a public URL from the provider to this API.
        "webhook_path": "/api/v1/email/webhook/resend",
        "webhook_configured": bool((settings.email_webhook_secret or "").strip()),
    }


@router.post("/email/send", status_code=status.HTTP_201_CREATED)
async def send(
    body: SendEmailRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    if body.contact_id is not None:
        contact = await session.get(Contact, body.contact_id)
        if contact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    try:
        return await send_email(
            session,
            user_id=current_user.id,
            to=str(body.to),
            subject=body.subject.strip(),
            text=body.text,
            html=body.html,
            reply_to=str(body.reply_to) if body.reply_to else None,
            contact_id=body.contact_id,
        )
    except EmailNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmailSendFailed as exc:
        # The provider's own words, so a bad domain or unverified sender is
        # diagnosable from the toast instead of a generic 500.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/email/messages")
async def messages(
    contact_id: int | None = Query(None, ge=1),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    return {"items": await list_sent_messages(session, contact_id=contact_id, limit=limit)}


# ---------------------------------------------------------------------------
# Delivery webhook
# ---------------------------------------------------------------------------
#
# Called by the provider, not by a browser: no session, no CSRF token, and the
# only thing standing between a stranger and the delivery status of every
# message is the signature. Hence: unverifiable events are refused outright
# rather than trusted.


@router.post("/email/webhook/{provider}", status_code=status.HTTP_202_ACCEPTED)
async def webhook(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if provider not in SUPPORTED_WEBHOOK_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown webhook provider")

    secret = (settings.email_webhook_secret or "").strip()
    if not secret:
        # Accepting unsigned events "to be helpful" would let anyone rewrite the
        # delivery status of every message, so the endpoint stays closed.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Delivery webhooks are disabled: set EMAIL_WEBHOOK_SECRET to enable them",
        )

    body = await request.body()
    try:
        webhooks.verify_signature(
            secret,
            svix_id=request.headers.get("svix-id"),
            svix_timestamp=request.headers.get("svix-timestamp"),
            svix_signature=request.headers.get("svix-signature"),
            body=body,
        )
    except webhooks.WebhookError as exc:
        logger.warning("Rejected %s webhook: %s", provider, exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature") from exc

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body is not JSON") from exc

    try:
        event = webhooks.parse_event(provider, payload)
    except webhooks.WebhookError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    message = await webhooks.apply_event(session, provider, event)
    await session.commit()
    if message is None:
        # Not an error: the message may predate this feature or belong to
        # another system on the same provider account.
        logger.info("No stored message for %s event %s", provider, event.get("message_id"))
    return {"received": True, "type": event["type"], "matched": message is not None}


# ---------------------------------------------------------------------------
# Gmail connect flow
# ---------------------------------------------------------------------------
#
# Google only returns a refresh token through a browser consent round-trip, so
# this is a real OAuth dance rather than a paste-a-key form. ``state`` is an
# HMAC over a nonce and an expiry, which is enough to stop a forged callback
# without storing anything server-side.


def _gmail_redirect_uri(request: Request) -> str:
    if settings.gmail_redirect_uri:
        return settings.gmail_redirect_uri
    return str(request.url_for("gmail_callback"))


def _require_gmail_client(config) -> None:
    """The OAuth client must exist before a consent round-trip is possible."""
    if not config.gmail_client_id or not config.gmail_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set gmail_client_id and gmail_client_secret before connecting Gmail",
        )


def _request_origin(request: Request) -> str | None:
    """The SPA origin this flow started from, when it is already allow-listed.

    The connect flow begins as a top-level navigation, so there is no ``Origin``
    header — only ``Referer``. Only origins in ``ALLOWED_ORIGINS`` are accepted,
    so a forged header cannot redirect the callback somewhere else.
    """
    raw = request.headers.get("origin") or request.headers.get("referer") or ""
    if not raw:
        return None
    parts = raw.split("/")
    if len(parts) < 3:
        return None
    origin = "/".join(parts[:3])
    return origin if origin in settings.allowed_origins else None


def _frontend_redirect(query: str, origin: str | None = None) -> RedirectResponse:
    """Return to the SPA that started the flow.

    Falling back to ``FRONTEND_URL`` matters in production; honouring the
    signed origin matters in development, where the app may be open on
    127.0.0.1 while the default points at localhost — a different cookie jar,
    which would silently sign the administrator out.
    """
    base = (origin if origin in settings.allowed_origins else None) or settings.frontend_url.rstrip("/")
    return RedirectResponse(f"{base}/#/settings?{query}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/email/gmail/authorize")
async def gmail_authorize(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(require_superuser),
):
    """Send the administrator to Google's consent screen."""
    config = await resolve_config(session)
    _require_gmail_client(config)
    # The nonce is not stored: ``sign_state`` makes the payload unforgeable, and
    # the expiry bounds replay, which is all a CSRF guard needs here.
    state = gmail_client.sign_state(
        settings.secret_key, secrets.token_urlsafe(16), _request_origin(request) or ""
    )
    url = gmail_client.authorization_url(
        client_id=config.gmail_client_id,
        redirect_uri=_gmail_redirect_uri(request),
        state=state,
    )
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/email/gmail/callback", name="gmail_callback")
async def gmail_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(require_superuser),
):
    """Exchange the authorization code and store the refresh token."""
    decoded = gmail_client.decode_state(settings.secret_key, state or "")
    if error:
        return _frontend_redirect(f"email=error&reason={quote(error)}", decoded and decoded["extra"])
    if decoded is None:
        # Expired or forged: refuse without touching Google.
        return _frontend_redirect(f"email=error&reason={quote('The connection request expired. Try again.')}")
    origin = decoded["extra"] or None
    if not code:
        return _frontend_redirect(
            f"email=error&reason={quote('Google did not return an authorization code.')}", origin
        )

    config = await resolve_config(session)
    _require_gmail_client(config)

    try:
        tokens = await gmail_client.exchange_code(
            client_id=config.gmail_client_id,
            client_secret=config.gmail_client_secret,
            code=code,
            redirect_uri=_gmail_redirect_uri(request),
        )
    except gmail_client.GmailError as exc:
        logger.warning("Gmail connect failed: %s", exc)
        return _frontend_redirect(f"email=error&reason={quote(str(exc))}", origin)

    sender = config.from_email or settings.gmail_sender or ""
    await _store_settings(
        session,
        {
            "gmail_refresh_token": tokens["refresh_token"],
            "gmail_sender": sender or None,
            # Selecting Gmail is implied by connecting it.
            "email_provider": "gmail",
        },
        current_user.id,
    )
    return _frontend_redirect("email=connected", origin)


@router.post("/email/gmail/disconnect", status_code=status.HTTP_200_OK)
async def gmail_disconnect(
    session: AsyncSession = Depends(get_session),
    current_user=Depends(require_superuser),
):
    """Forget the stored refresh token. Google's grant is left untouched."""
    await _store_settings(session, {"gmail_refresh_token": None}, current_user.id)
    return {"connected": False}


async def _store_settings(session: AsyncSession, values: dict[str, Any], user_id: int | None) -> None:
    """Upsert settings rows. A ``None`` value clears the row."""
    for key, value in values.items():
        row = (await session.execute(select(SettingsRow).where(SettingsRow.key == key))).scalar_one_or_none()
        if row is None:
            session.add(SettingsRow(key=key, value=value, updated_by_id=user_id))
        else:
            row.value = value
            row.updated_by_id = user_id
    await session.commit()
