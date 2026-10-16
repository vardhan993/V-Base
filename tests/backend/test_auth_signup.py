from __future__ import annotations


def test_signup_reachable(client):
    """Backend is up and the SPA-preferred POST /api/v1/auth/signup responds."""
    r = client.post("/api/v1/auth/signup", json={
        "email": "signup-check@example.com",
        "username": "signupcheck",
        "password": "passwordxyz123",
        "full_name": "Signup Check",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "session"
    assert body["email"] == "signup-check@example.com"
    assert body["access_token"]


def test_signup_duplicate_email_is_409(client):
    """Duplicate email returns 409, not a 500."""
    client.post("/api/v1/auth/signup", json={
        "email": "dup-check@example.com",
        "username": "dupcheck1",
        "password": "passwordxyz123",
    })
    r = client.post("/api/v1/auth/signup", json={
        "email": "dup-check@example.com",
        "username": "dupcheck2",
        "password": "passwordxyz123",
    })
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Email already registered"


def test_signup_without_origin_is_403(anonymous_client):
    """The CSRF middleware rejects origin-less unsafe requests."""
    r = anonymous_client.post("/api/v1/auth/signup", json={
        "email": "nosig@example.com",
        "username": "nosig",
        "password": "passwordxyz123",
    })
    assert r.status_code == 403
    assert r.json()["detail"] == "Missing Origin/Referer header"
