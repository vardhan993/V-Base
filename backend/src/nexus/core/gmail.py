"""Sending through the Gmail API on behalf of a connected Google account.

Why OAuth rather than SMTP: an app password can be revoked or blocked by a
workspace policy, and it cannot be scoped. The Gmail API issues a refresh token
that is limited to ``gmail.send`` — V-Base can send, and can do nothing else
with the mailbox (no read, no delete, no settings).

The flow is the standard offline one:

1. the operator registers an OAuth client and a redirect URI in Google Cloud;
2. ``GET /api/v1/email/gmail/authorize`` sends them to Google's consent screen;
3. Google redirects back to ``/api/v1/email/gmail/callback`` with a code;
4. the code is exchanged for a **refresh token**, which is the only credential
   stored. Every later send trades it for a short-lived access token.

Access tokens live in a small in-process cache, keyed by client id and refresh
token, so a burst of sends performs one token exchange rather than one per
message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from typing import Any
from urllib.parse import urlencode

import httpx

from nexus.core.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

#: Send-only. Asking for the full mailbox scope would be an unnecessary
#: liability for a CRM.
SCOPES = ("https://www.googleapis.com/auth/gmail.send", "openid", "email")

#: How long an authorization ``state`` stays valid, in seconds.
STATE_TTL_SECONDS = 600


class GmailError(RuntimeError):
    """Google rejected the request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GmailCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    sender: str


# ---------------------------------------------------------------------------
# CSRF state
# ---------------------------------------------------------------------------


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _encode_extra(extra: str) -> str:
    """base64url so the value can never contain the ``.`` field separator."""
    return base64.urlsafe_b64encode(extra.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_extra(encoded: str) -> str:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")


def sign_state(secret: str, nonce: str, extra: str = "") -> str:
    """``<nonce>.<expiry>.<extra>.<hmac>`` — stateless, so nothing is stored.

    ``extra`` carries the SPA origin the flow started from: signed, so the
    callback cannot be pointed at an arbitrary host.
    """
    expires = int(time.time()) + STATE_TTL_SECONDS
    payload = f"{nonce}.{expires}.{_encode_extra(extra)}"
    return f"{payload}.{_sign(secret, payload)}"


def decode_state(secret: str, state: str) -> dict[str, Any] | None:
    """Verified payload, or None when forged, malformed or expired."""
    parts = (state or "").split(".")
    if len(parts) != 4:
        return None
    nonce, expires, extra, signature = parts
    if not hmac.compare_digest(signature, _sign(secret, f"{nonce}.{expires}.{extra}")):
        return None
    try:
        if int(expires) < int(time.time()):
            return None
    except ValueError:
        return None
    try:
        decoded_extra = _decode_extra(extra)
    except (ValueError, UnicodeDecodeError):
        return None
    return {"nonce": nonce, "expires": int(expires), "extra": decoded_extra}


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    """Consent URL. ``prompt=consent`` is required to get a refresh token."""
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _google_error(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return f"{response.status_code} {response.reason_phrase}".strip()
    if isinstance(body, dict):
        description = body.get("error_description") or body.get("error")
        if description:
            return str(description)
    return f"{response.status_code} {response.reason_phrase}".strip()


async def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=settings.email_timeout_seconds) as client:
            response = await client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Google: {exc}") from exc
    if response.status_code >= 400:
        raise GmailError(_google_error(response), status_code=response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise GmailError("Google returned a response that was not JSON") from exc


async def exchange_code(*, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    """Trade an authorization code for tokens. Returns the whole token body."""
    body = await _post_form(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if not body.get("refresh_token"):
        # Google only returns a refresh token on the first consent for a client
        # (or when prompt=consent forces it). Without one, sending cannot work
        # once the access token expires, so treat it as a failure rather than
        # storing something that will break tomorrow.
        raise GmailError(
            "Google did not return a refresh token. Revoke V-Base's access at "
            "myaccount.google.com/permissions and connect again."
        )
    return body


def verify_state(secret: str, state: str) -> bool:
    """True when ``state`` is intact and unexpired."""
    return decode_state(secret, state) is not None


#: (client_id, refresh_token) -> (access_token, monotonic expiry)
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


def _cached_token(credentials: GmailCredentials) -> str | None:
    cached = _token_cache.get((credentials.client_id, credentials.refresh_token))
    if cached and cached[1] > time.monotonic():
        return cached[0]
    return None


async def access_token(credentials: GmailCredentials) -> str:
    """A bearer token, refreshed only when the cached one is close to expiry."""
    fresh = _cached_token(credentials)
    if fresh:
        return fresh

    body = await _post_form(
        TOKEN_URL,
        {
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": credentials.refresh_token,
            "grant_type": "refresh_token",
        },
    )
    token = body.get("access_token")
    if not token:
        raise GmailError("Google did not return an access token")
    # 60s of slack so a token cannot expire mid-request.
    _token_cache[(credentials.client_id, credentials.refresh_token)] = (
        token,
        time.monotonic() + max(0, int(body.get("expires_in") or 3600) - 60),
    )
    return token


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def build_raw_message(
    *, sender: str, to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None
) -> str:
    """base64url-encoded RFC 2822 message, as the Gmail API expects."""
    message = EmailMessage(policy=SMTP_POLICY)
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text)
    if html:
        # add_alternative after set_content produces a multipart/alternative with
        # the plain-text part first, which is what clients expect.
        message.add_alternative(html, subtype="html")
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


async def send(
    credentials: GmailCredentials,
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    token = await access_token(credentials)
    raw = build_raw_message(
        sender=credentials.sender, to=to, subject=subject, text=text, html=html, reply_to=reply_to
    )
    try:
        async with httpx.AsyncClient(timeout=settings.email_timeout_seconds) as client:
            response = await client.post(
                SEND_URL,
                json={"raw": raw},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise GmailError(f"Could not reach Gmail: {exc}") from exc

    if response.status_code >= 400:
        raise GmailError(_google_error(response), status_code=response.status_code)

    try:
        body = response.json()
    except ValueError:
        body = {}
    return {
        "id": body.get("id") if isinstance(body, dict) else None,
        "thread_id": body.get("threadId") if isinstance(body, dict) else None,
        "provider": "gmail",
        "status_code": response.status_code,
    }
