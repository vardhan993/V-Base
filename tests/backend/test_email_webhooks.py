"""Delivery webhooks: signature verification, parsing and status application."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from nexus.core import config as config_module
from nexus.core import email as email_module
from nexus.core import email_webhooks as webhooks

RAW_KEY = b"a-test-signing-key-value"
SECRET = "whsec_" + base64.b64encode(RAW_KEY).decode()


def svix_headers(body: bytes, *, timestamp: int | None = None, svix_id: str = "msg_1", key: bytes = RAW_KEY):
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signed = b".".join([svix_id.encode(), ts.encode(), body])
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": ts, "svix-signature": f"v1,{signature}"}


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_valid_signature_is_accepted():
    body = b'{"type":"email.delivered"}'
    headers = svix_headers(body)
    webhooks.verify_signature(
        SECRET,
        svix_id=headers["svix-id"],
        svix_timestamp=headers["svix-timestamp"],
        svix_signature=headers["svix-signature"],
        body=body,
    )


def test_a_single_flipped_byte_invalidates_the_signature():
    body = b'{"type":"email.delivered"}'
    headers = svix_headers(body)
    with pytest.raises(webhooks.WebhookError, match="signature does not match"):
        webhooks.verify_signature(
            SECRET,
            svix_id=headers["svix-id"],
            svix_timestamp=headers["svix-timestamp"],
            svix_signature=headers["svix-signature"],
            body=body + b" ",
        )


def test_signature_from_the_wrong_key_is_refused():
    body = b'{"type":"email.delivered"}'
    headers = svix_headers(body, key=b"a-different-key")
    with pytest.raises(webhooks.WebhookError):
        webhooks.verify_signature(
            SECRET,
            svix_id=headers["svix-id"],
            svix_timestamp=headers["svix-timestamp"],
            svix_signature=headers["svix-signature"],
            body=body,
        )


def test_a_replayed_old_timestamp_is_refused():
    body = b"{}"
    old = int(time.time()) - webhooks.TIMESTAMP_TOLERANCE.total_seconds() - 5
    headers = svix_headers(body, timestamp=int(old))
    with pytest.raises(webhooks.WebhookError, match="tolerance"):
        webhooks.verify_signature(
            SECRET,
            svix_id=headers["svix-id"],
            svix_timestamp=headers["svix-timestamp"],
            svix_signature=headers["svix-signature"],
            body=body,
        )


def test_missing_headers_are_refused():
    with pytest.raises(webhooks.WebhookError, match="Missing signature headers"):
        webhooks.verify_signature(SECRET, svix_id=None, svix_timestamp=None, svix_signature=None, body=b"{}")


def test_an_empty_secret_is_refused():
    with pytest.raises(webhooks.WebhookError, match="No webhook secret"):
        webhooks.verify_signature("", svix_id="i", svix_timestamp="1", svix_signature="v1,x", body=b"{}")


def test_rotation_style_multiple_signatures_are_accepted():
    body = b"{}"
    headers = svix_headers(body)
    combined = f"v1,bm90LWEtc2lnbmF0dXJl {headers['svix-signature']}"
    webhooks.verify_signature(
        SECRET,
        svix_id=headers["svix-id"],
        svix_timestamp=headers["svix-timestamp"],
        svix_signature=combined,
        body=body,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_event_normalises_a_resend_payload():
    event = webhooks.parse_event(
        "resend",
        {
            "type": "email.bounced",
            "created_at": "2026-10-14T01:00:00.000Z",
            "data": {"email_id": "abc123", "to": ["someone@example.com"], "subject": "Hi"},
        },
    )
    assert event["status"] == "bounced"
    assert event["message_id"] == "abc123"
    assert event["recipients"] == ["someone@example.com"]


def test_parse_event_tolerates_a_single_recipient():
    event = webhooks.parse_event("resend", {"type": "email.delivered", "data": {"to": "one@example.com"}})
    assert event["recipients"] == ["one@example.com"]


def test_parse_event_rejects_an_unknown_type():
    with pytest.raises(webhooks.WebhookError, match="no type"):
        webhooks.parse_event("resend", {"data": {}})


def test_parse_event_rejects_an_unknown_provider():
    with pytest.raises(webhooks.WebhookError, match="Unsupported"):
        webhooks.parse_event("carrier-pigeon", {"type": "email.sent"})


def test_unknown_event_types_do_not_change_the_status():
    # A provider adding a new event type must not blank out a known outcome.
    event = webhooks.parse_event("resend", {"type": "email.something_new", "data": {"email_id": "x"}})
    assert event["status"] is None


# ---------------------------------------------------------------------------
# API level
# ---------------------------------------------------------------------------


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_webhook_secret", SECRET)
    yield SECRET


def _send_an_email(auth_client, monkeypatch, provider_message_id: str) -> int:
    """Send through the regular endpoint so a tracked row exists."""
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")
    monkeypatch.setattr(config_module.settings, "email_api_key", "re_test_key")
    monkeypatch.setattr(config_module.settings, "email_from", "crm@example.com")

    async def fake_send_message(config, *, to, subject, text, html=None, reply_to=None):
        return {"id": provider_message_id, "provider": config.provider, "status_code": 200}

    monkeypatch.setattr(email_module, "send_message", fake_send_message)

    contact = auth_client.post(
        "/api/v1/contacts", json={"full_name": "Webhook Target", "email": "target@example.com"}
    ).json()
    sent = auth_client.post(
        "/api/v1/email/send",
        json={
            "to": "target@example.com",
            "subject": "Tracked",
            "text": "Body",
            "contact_id": contact["id"],
        },
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "sent"
    return contact["id"]


def test_webhook_is_disabled_without_a_secret(auth_client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_webhook_secret", "")
    response = auth_client.post("/api/v1/email/webhook/resend", content=b"{}")
    assert response.status_code == 503
    assert "EMAIL_WEBHOOK_SECRET" in response.json()["detail"]


def test_unknown_webhook_provider_is_a_404(auth_client, webhook_secret):
    assert auth_client.post("/api/v1/email/webhook/sendgrid", content=b"{}").status_code == 404


def test_webhook_rejects_a_forged_signature(auth_client, webhook_secret):
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "x"}}).encode()
    headers = {**svix_headers(body), "svix-signature": "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}
    response = auth_client.post("/api/v1/email/webhook/resend", content=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"


def test_webhook_updates_the_delivery_status(auth_client, webhook_secret, monkeypatch):
    contact_id = _send_an_email(auth_client, monkeypatch, "prov_msg_1")

    for event_type, expected in [
        ("email.sent", "sent"),
        ("email.delivered", "delivered"),
        ("email.opened", "opened"),
    ]:
        body = json.dumps(
            {"type": event_type, "data": {"email_id": "prov_msg_1", "to": ["target@example.com"]}}
        ).encode()
        response = auth_client.post("/api/v1/email/webhook/resend", content=body, headers=svix_headers(body))
        assert response.status_code == 202, response.text
        assert response.json()["matched"] is True

        listed = auth_client.get("/api/v1/email/messages", params={"contact_id": contact_id}).json()["items"]
        assert listed[0]["message_id"] == "prov_msg_1"
        assert listed[0]["status"] == expected
        assert listed[0]["last_event_at"] is not None


def test_a_bounce_wins_over_a_later_open(auth_client, webhook_secret, monkeypatch):
    contact_id = _send_an_email(auth_client, monkeypatch, "prov_msg_2")

    bounce = json.dumps({"type": "email.bounced", "data": {"email_id": "prov_msg_2"}}).encode()
    auth_client.post("/api/v1/email/webhook/resend", content=bounce, headers=svix_headers(bounce))
    # Some clients prefetch pixels; the bounce is still the truth.
    opened = json.dumps({"type": "email.opened", "data": {"email_id": "prov_msg_2"}}).encode()
    auth_client.post("/api/v1/email/webhook/resend", content=opened, headers=svix_headers(opened))

    listed = auth_client.get("/api/v1/email/messages", params={"contact_id": contact_id}).json()["items"]
    assert listed[0]["status"] == "bounced"


def test_an_unmatched_event_is_accepted_but_not_applied(auth_client, webhook_secret):
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "not-ours"}}).encode()
    response = auth_client.post("/api/v1/email/webhook/resend", content=body, headers=svix_headers(body))
    assert response.status_code == 202
    assert response.json()["matched"] is False


def test_a_non_json_body_is_rejected(auth_client, webhook_secret):
    body = b"not json at all"
    response = auth_client.post("/api/v1/email/webhook/resend", content=body, headers=svix_headers(body))
    assert response.status_code == 400
    assert "not JSON" in response.json()["detail"]


def test_status_reports_the_webhook_configuration(auth_client, webhook_secret):
    payload = auth_client.get("/api/v1/email/status").json()
    assert payload["webhook_configured"] is True
    assert payload["webhook_path"] == "/api/v1/email/webhook/resend"


def test_webhook_is_reachable_without_a_browser_origin(anonymous_client, webhook_secret):
    """A provider posts server-to-server: no Origin and no CSRF token.

    The CSRF middleware rejects an unsafe ``/api/`` request that carries
    neither header, so this path has to be exempt or every real delivery event
    would be refused with 403 before the signature is even checked. The
    browser-like client used elsewhere injects both headers, so only a bare
    client proves it.
    """
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "x"}}).encode()
    response = anonymous_client.post(
        "/api/v1/email/webhook/resend", content=body, headers=svix_headers(body)
    )
    # 202 (accepted, unmatched) — anything but the middleware's 403.
    assert response.status_code == 202, response.text


def test_a_different_api_path_still_requires_an_origin(anonymous_client):
    """The exemption must be scoped to the webhook, not to all of /api/."""
    response = anonymous_client.post("/api/v1/contacts", json={"full_name": "Blocked"})
    assert response.status_code == 403
    assert "Origin" in response.json()["detail"]
