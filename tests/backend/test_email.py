"""Outbound email: configuration resolution, sending and the activity trail."""

from __future__ import annotations

import httpx
import pytest

from nexus.core import config as config_module
from nexus.core import email as email_module


@pytest.fixture
def configured_email(monkeypatch):
    """Pretend the deployment supplied a key and a From address in the env."""
    monkeypatch.setattr(config_module.settings, "email_api_key", "re_test_key")
    monkeypatch.setattr(config_module.settings, "email_from", "crm@example.com")
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")


def test_provider_error_prefers_the_message_field():
    response = httpx.Response(403, json={"message": "domain is not verified"}, request=httpx.Request("POST", "https://x"))
    assert email_module._provider_error(response) == "domain is not verified"


def test_provider_error_reads_a_nested_error():
    response = httpx.Response(
        422,
        json={"error": {"message": "invalid to field"}},
        request=httpx.Request("POST", "https://x"),
    )
    assert email_module._provider_error(response) == "invalid to field"


def test_provider_error_falls_back_to_the_status_line():
    response = httpx.Response(500, text="<html>boom</html>", request=httpx.Request("POST", "https://x"))
    assert "500" in email_module._provider_error(response)


def test_status_reports_missing_settings(auth_client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")
    monkeypatch.setattr(config_module.settings, "email_api_key", "")
    monkeypatch.setattr(config_module.settings, "email_from", "")

    body = auth_client.get("/api/v1/email/status")
    assert body.status_code == 200
    payload = body.json()
    assert payload["configured"] is False
    assert "email_api_key" in payload["missing"]
    assert "email_from" in payload["missing"]
    # The key itself must never be echoed, only where it came from.
    assert "api_key" not in payload
    assert payload["credential_source"] == "none"


def test_status_hides_the_api_key(auth_client, configured_email):
    payload = auth_client.get("/api/v1/email/status").json()
    assert payload["configured"] is True
    assert payload["credential_source"] == "environment"
    assert payload["from_email"] == "crm@example.com"
    assert "re_test_key" not in str(payload)


def test_send_is_refused_when_not_configured(auth_client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")
    monkeypatch.setattr(config_module.settings, "email_api_key", "")
    monkeypatch.setattr(config_module.settings, "email_from", "")

    response = auth_client.post(
        "/api/v1/email/send",
        json={"to": "someone@example.com", "subject": "Hi", "text": "Body"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "not configured" in detail
    # The refusal must name what is missing so setup is actionable.
    assert "email_api_key" in detail


def test_send_validates_the_recipient(auth_client, configured_email):
    response = auth_client.post(
        "/api/v1/email/send",
        json={"to": "not-an-email", "subject": "Hi", "text": "Body"},
    )
    assert response.status_code == 422


def test_send_rejects_an_unknown_contact(auth_client, configured_email):
    response = auth_client.post(
        "/api/v1/email/send",
        json={"to": "someone@example.com", "subject": "Hi", "text": "Body", "contact_id": 999999},
    )
    assert response.status_code == 404


def test_send_records_the_message_on_the_contact(auth_client, configured_email, monkeypatch):
    calls: list[dict] = []

    async def fake_send_message(config, *, to, subject, text, html=None, reply_to=None):
        calls.append({"to": to, "subject": subject, "text": text, "provider": config.provider})
        return {"id": "msg_123", "provider": config.provider, "status_code": 200}

    monkeypatch.setattr(email_module, "send_message", fake_send_message)

    contact = auth_client.post(
        "/api/v1/contacts", json={"full_name": "Email Target", "email": "target@example.com"}
    ).json()

    sent = auth_client.post(
        "/api/v1/email/send",
        json={
            "to": "target@example.com",
            "subject": "Following up",
            "text": "Just checking in.",
            "contact_id": contact["id"],
        },
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["id"] == "msg_123"
    assert body["provider"] == "resend"
    assert body["to"] == "target@example.com"

    # The provider received exactly one call with the composed message.
    assert len(calls) == 1
    assert calls[0]["subject"] == "Following up"

    history = auth_client.get("/api/v1/email/messages", params={"contact_id": contact["id"]})
    assert history.status_code == 200
    items = history.json()["items"]
    assert any(m["subject"] == "Following up" and m["message_id"] == "msg_123" for m in items)

    # Other contacts' timelines stay clean.
    other = auth_client.get("/api/v1/email/messages", params={"contact_id": 999999})
    assert other.json()["items"] == []


def test_send_surfaces_the_provider_refusal(auth_client, configured_email, monkeypatch):
    async def refuse(config, *, to, subject, text, html=None, reply_to=None):
        raise email_module.EmailSendFailed("domain is not verified", status_code=403)

    monkeypatch.setattr(email_module, "send_message", refuse)

    response = auth_client.post(
        "/api/v1/email/send",
        json={"to": "target@example.com", "subject": "Hi", "text": "Body"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "domain is not verified"


def test_send_rejects_an_unsupported_provider(auth_client, configured_email, monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_provider", "carrier-pigeon")
    response = auth_client.post(
        "/api/v1/email/send",
        json={"to": "target@example.com", "subject": "Hi", "text": "Body"},
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


def test_activity_trail_records_the_send(auth_client, configured_email, monkeypatch):
    async def ok(config, *, to, subject, text, html=None, reply_to=None):
        return {"id": "msg_activity", "provider": config.provider, "status_code": 200}

    monkeypatch.setattr(email_module, "send_message", ok)

    auth_client.post(
        "/api/v1/email/send",
        json={"to": "trail@example.com", "subject": "Trail check", "text": "Body"},
    )
    feed = auth_client.get("/api/v1/activity", params={"action": "email_sent"}).json()
    assert any(item["description"] == "Emailed trail@example.com: Trail check" for item in feed["items"])
