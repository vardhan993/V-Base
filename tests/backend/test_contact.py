"""Tests for the public landing-page contact endpoint."""

from __future__ import annotations


def _post(client, **overrides):
    """POST with a unique client IP per call, so rate-limit windows are isolated."""
    import itertools
    import uuid

    counter = itertools.count()
    headers = {"X-Forwarded-For": f"10.1.{next(counter)}.{uuid.uuid4().int % 254 + 1}"}
    return client.post("/api/v1/contact", json={**VALID, **overrides}, headers=headers)

VALID = {
    "name": "Jane Cooper",
    "email": "jane@company.example",
    "company": "Company Ltd",
    "message": "We would like to migrate 9,000 rows to V-Base next week.",
}


def test_contact_message_stored(auth_client, client):
    """A valid submission is stored (id > 0); the response says received.

    202 means stored-but-forward-pending (no provider in the test env) — the
    lead is still on disk, which is the contract.
    """
    response = _post(client)
    assert response.status_code in (201, 202), response.text
    body = response.json()
    assert body["received"] is True
    assert body["id"] > 0


def test_contact_rejects_honeypot(client):
    response = _post(client, website="http://spam.example")
    # Honeypot trips the Pydantic max_length=0 constraint -> 422.
    assert response.status_code == 422


def test_contact_rejects_links_in_message(client):
    response = _post(client, message="Visit https://spam.example now please")
    assert response.status_code == 422


def test_contact_rejects_short_message(client):
    response = _post(client, message="hi there")
    assert response.status_code == 422


def test_contact_rate_limited(client):
    sentinel = "198.51.100.7"
    for _ in range(5):
        last = client.post("/api/v1/contact", json=VALID, headers={"X-Forwarded-For": sentinel})
        assert last.status_code in (201, 202), last.text
    sixth = client.post("/api/v1/contact", json=VALID, headers={"X-Forwarded-For": sentinel})
    assert sixth.status_code == 429
    assert "Retry-After" in sixth.headers


def test_heuristic_spam_returns_fake_success(client):
    """Spam-shaped input gets an indistinguishable success with id 0."""
    response = _post(client, name="Buy Now http://spam.example")
    assert response.status_code in (201, 202)
    assert response.json()["id"] == 0
