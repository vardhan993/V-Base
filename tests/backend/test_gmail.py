"""Gmail sending: message construction, OAuth handling and the connect flow."""

from __future__ import annotations

import base64
import time
from email import message_from_bytes, policy
from urllib.parse import parse_qs, urlparse

import pytest

from nexus.core import config as config_module
from nexus.core import email as email_module
from nexus.core import gmail as gmail_client

from .conftest import run_sql

# ---------------------------------------------------------------------------
# Message construction (no network)
# ---------------------------------------------------------------------------


def test_raw_message_is_a_valid_rfc2822_document():
    raw = gmail_client.build_raw_message(
        sender="V-Base <crm@example.com>",
        to="target@example.com",
        subject="Following up",
        text="Just checking in.",
    )
    decoded = base64.urlsafe_b64decode(raw)
    # The default policy is required for the modern parse API (get_content,
    # iter_parts); the compat32 default would raise AttributeError.
    parsed = message_from_bytes(decoded, policy=policy.default)

    assert parsed["From"] == "V-Base <crm@example.com>"
    assert parsed["To"] == "target@example.com"
    assert parsed["Subject"] == "Following up"
    assert parsed.get_content().strip() == "Just checking in."
    # SMTP policy means CRLF line endings, which is what the API expects.
    assert b"\r\n" in decoded


def test_raw_message_builds_a_multipart_alternative_with_html():
    raw = gmail_client.build_raw_message(
        sender="crm@example.com",
        to="target@example.com",
        subject="Rich",
        text="Plain part",
        html="<p>HTML part</p>",
        reply_to="reply@example.com",
    )
    parsed = message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)

    assert parsed.get_content_type() == "multipart/alternative"
    subtypes = {part.get_content_type() for part in parsed.iter_parts()}
    assert subtypes == {"text/plain", "text/html"}
    assert parsed["Reply-To"] == "reply@example.com"


def test_raw_message_survives_a_non_ascii_subject():
    raw = gmail_client.build_raw_message(
        sender="crm@example.com", to="t@example.com", subject="Réunion — café", text="ok"
    )
    parsed = message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)
    assert parsed["Subject"] == "Réunion — café"


# ---------------------------------------------------------------------------
# OAuth state
# ---------------------------------------------------------------------------


def test_state_round_trips_and_rejects_tampering():
    state = gmail_client.sign_state("secret-key", "nonce")
    assert gmail_client.verify_state("secret-key", state) is True
    assert gmail_client.verify_state("other-key", state) is False
    # The mutation must be guaranteed non-identical: when the signature's last
    # hex char happens to be "0", replacing it with "0" would leave the state
    # unchanged and verification would (correctly) succeed.
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")
    assert tampered != state
    assert gmail_client.verify_state("secret-key", tampered) is False
    assert gmail_client.verify_state("secret-key", "not-a-state") is False
    assert gmail_client.verify_state("secret-key", "") is False


def test_state_carries_the_starting_origin_under_signature():
    state = gmail_client.sign_state("secret-key", "nonce", "http://127.0.0.1:5173")
    decoded = gmail_client.decode_state("secret-key", state)
    assert decoded is not None
    assert decoded["extra"] == "http://127.0.0.1:5173"

    # Substituting another origin invalidates the signature.
    other = gmail_client.sign_state("secret-key", "nonce", "https://evil.example")
    parts, other_parts = state.split("."), other.split(".")
    forged = ".".join([parts[0], parts[1], other_parts[2], parts[3]])
    assert gmail_client.decode_state("secret-key", forged) is None


def test_decode_state_rejects_malformed_input():
    assert gmail_client.decode_state("k", "") is None
    assert gmail_client.decode_state("k", "a.b") is None
    assert gmail_client.decode_state("k", "a.b.c") is None


def test_expired_state_is_refused(monkeypatch):
    monkeypatch.setattr(gmail_client.time, "time", lambda: 1_000_000)
    state = gmail_client.sign_state("secret-key", "nonce")
    monkeypatch.setattr(gmail_client.time, "time", lambda: 1_000_000 + gmail_client.STATE_TTL_SECONDS + 1)
    assert gmail_client.verify_state("secret-key", state) is False


def test_authorization_url_requests_offline_send_only_access():
    url = gmail_client.authorization_url(
        client_id="cid.apps.googleusercontent.com",
        redirect_uri="https://api.example.com/api/v1/email/gmail/callback",
        state="st",
    )
    assert url.startswith(gmail_client.AUTHORIZE_URL)
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "response_type=code" in url
    # Send-only scope: the CRM must not be able to read the mailbox.
    assert "gmail.send" in url
    assert "gmail.readonly" not in url
    assert "state=st" in url


# ---------------------------------------------------------------------------
# Token handling
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    @property
    def reason_phrase(self) -> str:
        return "OK" if self.status_code < 400 else "Bad Request"

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Stands in for ``httpx.AsyncClient`` so no request leaves the process.

    Responses are routed by URL, because a real send performs two calls: a
    token refresh and then the message.
    """

    calls: list[dict] = []
    responses: dict[str, _FakeResponse] = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        _FakeClient.calls.append({"url": url, **kwargs})
        return _FakeClient.responses.get(url) or _FakeResponse(500, {"error": f"unexpected POST to {url}"})


@pytest.fixture
def fake_http(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.responses = {
        gmail_client.TOKEN_URL: _FakeResponse(200, {"access_token": "at", "expires_in": 3600}),
        gmail_client.SEND_URL: _FakeResponse(200, {"id": "msg_1", "threadId": "thr_1"}),
    }
    monkeypatch.setattr(gmail_client.httpx, "AsyncClient", _FakeClient)
    # The access-token cache is process-wide; clear it so tests stay independent.
    gmail_client._token_cache.clear()
    yield _FakeClient
    gmail_client._token_cache.clear()


def credentials() -> gmail_client.GmailCredentials:
    return gmail_client.GmailCredentials(
        client_id="cid", client_secret="csecret", refresh_token="rtok", sender="crm@example.com"
    )


async def test_access_token_is_cached_between_sends(fake_http):
    first = await gmail_client.access_token(credentials())
    second = await gmail_client.access_token(credentials())

    assert first == second == "at"
    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["url"] == gmail_client.TOKEN_URL
    assert fake_http.calls[0]["data"]["grant_type"] == "refresh_token"


async def test_access_token_refreshes_when_expired(fake_http):
    await gmail_client.access_token(credentials())
    # Force the cached entry to look stale.
    key = ("cid", "rtok")
    gmail_client._token_cache[key] = ("old", time.monotonic() - 1)
    await gmail_client.access_token(credentials())
    assert len(fake_http.calls) == 2


async def test_exchange_code_requires_a_refresh_token(fake_http):
    fake_http.responses[gmail_client.TOKEN_URL] = _FakeResponse(200, {"access_token": "at"})
    with pytest.raises(gmail_client.GmailError, match="refresh token"):
        await gmail_client.exchange_code(client_id="cid", client_secret="s", code="c", redirect_uri="r")


async def test_google_errors_are_surfaced(fake_http):
    fake_http.responses[gmail_client.TOKEN_URL] = _FakeResponse(
        401, {"error": "invalid_grant", "error_description": "Token has been expired"}
    )
    with pytest.raises(gmail_client.GmailError, match="Token has been expired"):
        await gmail_client.access_token(credentials())


async def test_send_posts_the_raw_message_with_a_bearer_token(fake_http):
    result = await gmail_client.send(credentials(), to="t@example.com", subject="Hi", text="Body")

    assert result["id"] == "msg_1"
    assert result["provider"] == "gmail"
    # One token refresh, then the message.
    assert [call["url"] for call in fake_http.calls] == [gmail_client.TOKEN_URL, gmail_client.SEND_URL]
    call = fake_http.calls[1]
    assert call["headers"]["Authorization"] == "Bearer at"
    parsed = message_from_bytes(base64.urlsafe_b64decode(call["json"]["raw"]), policy=policy.default)
    assert parsed["Subject"] == "Hi"
    assert parsed["To"] == "t@example.com"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def gmail_settings(monkeypatch, **values):
    monkeypatch.setattr(config_module.settings, "email_provider", "gmail")
    monkeypatch.setattr(config_module.settings, "gmail_client_id", values.get("client_id", "cid"))
    monkeypatch.setattr(config_module.settings, "gmail_client_secret", values.get("client_secret", "csecret"))
    monkeypatch.setattr(config_module.settings, "gmail_refresh_token", values.get("refresh_token", "rtok"))
    monkeypatch.setattr(config_module.settings, "gmail_sender", values.get("sender", "crm@example.com"))
    monkeypatch.setattr(config_module.settings, "email_api_key", "")
    monkeypatch.setattr(config_module.settings, "email_from", "")
    monkeypatch.setattr(config_module.settings, "gmail_redirect_uri", "")


def test_status_reports_gmail_specific_gaps(auth_client, monkeypatch):
    gmail_settings(monkeypatch, refresh_token="")

    payload = auth_client.get("/api/v1/email/status").json()
    assert payload["provider"] == "gmail"
    assert payload["configured"] is False
    assert "gmail_refresh_token" in payload["missing"]
    assert payload["gmail_connect_url"] == "/api/v1/email/gmail/authorize"
    assert payload["gmail_connected"] is False
    # Credentials must never come back out.
    assert "csecret" not in str(payload)


def test_status_lists_both_providers(auth_client, monkeypatch):
    gmail_settings(monkeypatch, refresh_token="")
    payload = auth_client.get("/api/v1/email/status").json()
    assert set(payload["supported_providers"]) == {"resend", "gmail"}


async def test_send_routes_through_gmail(auth_client, monkeypatch):
    gmail_settings(monkeypatch)
    sent: list[dict] = []

    async def fake_send(creds, *, to, subject, text, html=None, reply_to=None):
        sent.append({"creds": creds, "to": to, "subject": subject})
        return {"id": "gmail_msg", "provider": "gmail", "status_code": 200}

    monkeypatch.setattr(email_module.gmail_client, "send", fake_send)

    response = auth_client.post(
        "/api/v1/email/send", json={"to": "target@example.com", "subject": "Via Gmail", "text": "Body"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["provider"] == "gmail"
    assert response.json()["id"] == "gmail_msg"
    assert sent and sent[0]["creds"].refresh_token == "rtok"


def test_unsupported_provider_is_refused(auth_client, monkeypatch):
    gmail_settings(monkeypatch)
    monkeypatch.setattr(config_module.settings, "email_provider", "carrier-pigeon")
    response = auth_client.post("/api/v1/email/send", json={"to": "t@example.com", "subject": "s", "text": "b"})
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Connect flow (API level)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(signed_up):
    """The connect flow is an org-wide credential, so it needs an admin."""
    client, user = signed_up
    run_sql("UPDATE users SET is_superuser = true WHERE email = :email", {"email": user["email"]})
    return client, user


def test_authorize_requires_the_oauth_client(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch, client_id="", client_secret="")

    response = client.get("/api/v1/email/gmail/authorize", follow_redirects=False)
    assert response.status_code == 400
    assert "gmail_client_id" in response.json()["detail"]


def test_authorize_redirects_to_google(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch)

    response = client.get("/api/v1/email/gmail/authorize", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith(gmail_client.AUTHORIZE_URL)
    assert "gmail.send" in location
    assert "state=" in location


def test_authorize_is_admin_only(auth_client, monkeypatch):
    gmail_settings(monkeypatch)
    assert auth_client.get("/api/v1/email/gmail/authorize", follow_redirects=False).status_code == 403


def test_callback_reports_a_user_cancelled_consent(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch)

    response = client.get(
        "/api/v1/email/gmail/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "email=error" in response.headers["location"]
    assert "access_denied" in response.headers["location"]


def test_callback_refuses_a_forged_state(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch)
    called = False

    async def should_not_run(**kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(gmail_client, "exchange_code", should_not_run)

    response = client.get(
        "/api/v1/email/gmail/callback",
        params={"code": "abc", "state": "forged.state.sig"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "email=error" in response.headers["location"]
    # Google must not be contacted when the state does not verify.
    assert called is False


def test_callback_stores_the_refresh_token_and_selects_gmail(admin_client, monkeypatch):
    client, user = admin_client
    gmail_settings(monkeypatch, refresh_token="")

    async def fake_exchange(**kwargs):
        assert kwargs["code"] == "auth-code"
        return {"refresh_token": "stored-rtok", "access_token": "at"}

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    state = gmail_client.sign_state(config_module.settings.secret_key, "nonce")
    response = client.get(
        "/api/v1/email/gmail/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "email=connected" in response.headers["location"]

    # The token landed in the settings table, not in the response.
    rows = run_sql("SELECT value FROM settings WHERE key = 'gmail_refresh_token'")
    assert rows and rows[0]["value"] == "stored-rtok"
    assert "stored-rtok" not in response.headers["location"]

    # Env still has no token, so the stored one is what makes it configured.
    monkeypatch.setattr(config_module.settings, "gmail_refresh_token", "")
    payload = client.get("/api/v1/email/status").json()
    assert payload["gmail_connected"] is True
    assert payload["credential_source"] == "settings"
    assert payload["configured"] is True


def _state_from_authorize(client, start_origin: str) -> str:
    """Run the first leg and read the signed state back out of the redirect.

    The header is set explicitly: the test client injects its own ``Origin``,
    and a real browser navigation would carry only ``Referer``. Both are read by
    the endpoint, and an explicit header proves the value is carried through.
    """
    response = client.get(
        "/api/v1/email/gmail/authorize",
        headers={"Origin": start_origin, "Referer": f"{start_origin}/#/settings"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307), response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0]


def test_callback_returns_to_the_origin_that_started_the_flow(admin_client, monkeypatch):
    """A dev session on 127.0.0.1 must not be bounced to localhost.

    They are different cookie jars, so redirecting to FRONTEND_URL would log the
    administrator out and lose the result of the connection they just made.
    """
    client, _ = admin_client
    gmail_settings(monkeypatch, refresh_token="")

    async def fake_exchange(**kwargs):
        return {"refresh_token": "rtok"}

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    state = _state_from_authorize(client, "http://127.0.0.1:5173")
    done = client.get(
        "/api/v1/email/gmail/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert done.status_code == 303
    assert done.headers["location"].startswith("http://127.0.0.1:5173/#/settings?email=connected")


def test_callback_falls_back_for_an_unlisted_origin(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch, refresh_token="")

    async def fake_exchange(**kwargs):
        return {"refresh_token": "rtok"}

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    # A host we do not recognise must not be able to steer the redirect.
    state = _state_from_authorize(client, "https://evil.example")
    done = client.get(
        "/api/v1/email/gmail/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    location = done.headers["location"]
    assert "evil.example" not in location
    assert location.startswith(config_module.settings.frontend_url.rstrip("/"))


def test_disconnect_clears_the_token(admin_client, monkeypatch):
    client, _ = admin_client
    gmail_settings(monkeypatch, refresh_token="")

    async def fake_exchange(**kwargs):
        return {"refresh_token": "stored-rtok"}

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)
    state = gmail_client.sign_state(config_module.settings.secret_key, "nonce")
    client.get(
        "/api/v1/email/gmail/callback", params={"code": "c", "state": state}, follow_redirects=False
    )

    response = client.post("/api/v1/email/gmail/disconnect")
    assert response.status_code == 200
    assert response.json() == {"connected": False}

    monkeypatch.setattr(config_module.settings, "gmail_refresh_token", "")
    payload = client.get("/api/v1/email/status").json()
    assert payload["gmail_connected"] is False
    assert "gmail_refresh_token" in payload["missing"]


def test_gmail_credentials_never_appear_in_status_or_logs(auth_client, monkeypatch):
    gmail_settings(monkeypatch, refresh_token="super-secret-refresh")
    payload = auth_client.get("/api/v1/email/status")
    assert "super-secret-refresh" not in payload.text
    assert "csecret" not in payload.text

