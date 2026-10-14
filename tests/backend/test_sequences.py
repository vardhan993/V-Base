"""Email sequences: rendering, the dispatcher clock and enrollment lifecycle.

These run against real PostgreSQL because the interesting parts are the
scheduler's queries — the due ordering, the FOR UPDATE that stops two replicas
claiming the same row, and the cascade when a sequence is deleted.
"""

from __future__ import annotations

import pytest

from nexus.core import config as config_module
from nexus.core import email as email_module
from nexus.core import sequences as sequences_module
from nexus.database import Company, Contact

from .conftest import run_sql, unique


@pytest.fixture()
def configured_email(monkeypatch):
    """Pretend the deployment supplied a key and a From address in the env."""
    monkeypatch.setattr(config_module.settings, "email_api_key", "re_test_key")
    monkeypatch.setattr(config_module.settings, "email_from", "crm@example.com")
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")


@pytest.fixture()
def provider(monkeypatch):
    """A provider that accepts everything and records what it was given."""
    calls: list[dict] = []

    async def fake_send_message(config, *, to, subject, text, html=None, reply_to=None):
        calls.append({"to": to, "subject": subject, "text": text})
        return {"id": f"msg_{len(calls)}", "provider": config.provider, "status_code": 200}

    monkeypatch.setattr(email_module, "send_message", fake_send_message)
    return calls


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _contact(**fields) -> Contact:
    defaults = {"first_name": "Ishita", "last_name": "Rao", "email": "ishita@acme.example", "company_name": "Acme"}
    return Contact(id=1, **{**defaults, **fields})


def test_render_expands_every_documented_variable():
    text = sequences_module.render(
        "Hi {{first_name}} {{last_name}},\n\n{{job_title}} at {{company}} in {{city}} ({{email}}).",
        _contact(job_title="Head of Data", city="Hyderabad"),
    )
    assert "Hi Ishita Rao," in text
    assert "Head of Data at Acme in Hyderabad (ishita@acme.example)." in text


def test_render_is_case_and_space_tolerant():
    assert sequences_module.render("Hello {{ First_Name }}", _contact()) == "Hello Ishita"
    assert sequences_module.render("Hello {{FIRST_NAME}}", _contact()) == "Hello Ishita"


def test_render_leaves_an_unknown_token_visible():
    """A typo must be obvious, not silently blanked into a worse email."""
    assert sequences_module.render("Hi {{frist_name}}", _contact()) == "Hi {{frist_name}}"


def test_render_blanks_a_missing_field():
    assert sequences_module.render("[{{city}}]", _contact()) == "[]"


def test_render_falls_back_to_the_full_name_when_the_parts_are_missing():
    """Most CRM records carry one full name, not two fields."""
    only_full = _contact(first_name=None, last_name=None, full_name="Ishita Rao")
    assert sequences_module.render("Hi {{first_name}} {{last_name}}", only_full) == "Hi Ishita Rao"
    single = _contact(first_name=None, last_name=None, full_name="Cher")
    assert sequences_module.render("Hi {{first_name}} [{{last_name}}]", single) == "Hi Cher []"


def test_render_uses_the_company_relationship_when_there_is_one():
    sequence_contact = _contact(company_name="Denormalised Co")
    sequence_contact.company = Company(name="Joined Co")
    assert sequences_module.render("{{company}}", sequence_contact) == "Joined Co"


# ---------------------------------------------------------------------------
# Sequences CRUD
# ---------------------------------------------------------------------------


def _create_sequence(auth_client, name: str = "Cold follow-up", steps: list[dict] | None = None):
    payload = {"name": name, "steps": steps if steps is not None else []}
    response = auth_client.post("/api/v1/sequences", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_contact(auth_client, name: str | None = None, email: str | None = None, **extra):
    body = {"full_name": name or "Ishita Rao", **extra}
    if email:
        body["email"] = email
    response = auth_client.post("/api/v1/contacts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_sequence_stores_the_steps_in_order(auth_client):
    created = _create_sequence(
        auth_client,
        steps=[
            {"delay_days": 0, "subject": "Hello", "body": "First"},
            {"delay_days": 3, "subject": "Nudge", "body": "Second"},
        ],
    )
    assert created["step_count"] == 2
    assert [step["position"] for step in created["steps"]] == [0, 1]
    assert created["steps"][1]["delay_days"] == 3
    assert created["is_active"] is True


def test_sequence_list_reports_the_variables_an_author_can_use(auth_client):
    payload = auth_client.get("/api/v1/sequences").json()
    assert "first_name" in payload["variables"]
    assert payload["max_steps"] >= 5


def test_replacing_steps_drops_the_old_ones(auth_client):
    created = _create_sequence(auth_client, steps=[{"delay_days": 0, "subject": "Old", "body": "Old body"}])
    updated = auth_client.patch(
        f"/api/v1/sequences/{created['id']}",
        json={"steps": [{"delay_days": 7, "subject": "New", "body": "New body"}]},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["step_count"] == 1
    assert body["steps"][0]["subject"] == "New"
    # Only the replacement is left in the database, not both.
    rows = run_sql(
        "SELECT subject FROM email_sequence_steps WHERE sequence_id = :id ORDER BY position",
        {"id": created["id"]},
    )
    assert [row["subject"] for row in rows] == ["New"]


def test_deleting_a_sequence_removes_its_enrollments(auth_client):
    created = _create_sequence(auth_client, steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, email=f"{unique('e')}@example.com")
    enrolled = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert enrolled.status_code == 201, enrolled.text

    deleted = auth_client.delete(f"/api/v1/sequences/{created['id']}")
    assert deleted.status_code == 200
    assert auth_client.get(f"/api/v1/sequences/{created['id']}").status_code == 404
    assert (
        run_sql("SELECT count(*) AS n FROM email_sequence_steps WHERE sequence_id = :id", {"id": created["id"]})[0]["n"]
        == 0
    )
    assert (
        run_sql("SELECT count(*) AS n FROM email_sequence_enrollments WHERE sequence_id = :id", {"id": created["id"]})[
            0
        ]["n"]
        == 0
    )


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


def test_enroll_refuses_a_sequence_with_no_steps(auth_client):
    created = _create_sequence(auth_client)
    contact = _create_contact(auth_client, email="someone@example.com")
    response = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert response.status_code == 400
    assert "step" in response.json()["detail"].lower()


def test_enroll_refuses_a_contact_without_an_email(auth_client):
    created = _create_sequence(auth_client, steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, name="No Email")
    response = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


def test_enroll_refuses_a_second_live_enrollment(auth_client):
    created = _create_sequence(auth_client, steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, email="someone@example.com")

    enrollment = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert enrollment.status_code == 201, enrollment.text
    again = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert again.status_code == 409


def test_a_completed_contact_can_be_enrolled_again(auth_client):
    """Re-arming a finished sequence is a normal thing to want."""
    created = _create_sequence(auth_client, steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, email="someone@example.com")
    enrollment = auth_client.post(
        f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]}
    ).json()

    auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "cancelled"})
    again = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert again.status_code == 201
    assert again.json()["status"] == "active"
    assert again.json()["id"] != enrollment["id"]


def test_enrollment_is_visible_on_the_contact(auth_client):
    created = _create_sequence(auth_client, name="Intro", steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, email="someone@example.com")
    auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})

    items = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"]
    assert len(items) == 1
    assert items[0]["sequence_name"] == "Intro"
    assert items[0]["contact_email"] == "someone@example.com"
    # A second contact's list stays empty.
    other = _create_contact(auth_client, email="other@example.com")
    assert auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": other["id"]}).json()["items"] == []


def test_enrolling_appears_in_the_activity_trail(auth_client):
    created = _create_sequence(auth_client, name="Intro", steps=[{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    contact = _create_contact(auth_client, email="someone@example.com")
    auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})

    feed = auth_client.get("/api/v1/activity", params={"action": "sequence_enrolled"}).json()
    assert any(item["description"] == "Enrolled in sequence: Intro" for item in feed["items"])


# ---------------------------------------------------------------------------
# The dispatcher clock
# ---------------------------------------------------------------------------


def _due_enrollment(auth_client, steps, *, name: str = "Cold follow-up"):
    created = _create_sequence(auth_client, name=name, steps=steps)
    contact = _create_contact(auth_client, email=f"{unique('e')}@example.com")
    response = auth_client.post(f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]})
    assert response.status_code == 201, response.text
    return created, contact, response.json()


def test_dispatch_sends_the_first_step_immediately_and_schedules_the_next(auth_client, configured_email, provider):
    contact = _create_contact(auth_client, email=f"{unique('e')}@example.com", company_name="Acme")
    created = _create_sequence(
        auth_client,
        steps=[
            {"delay_days": 0, "subject": "Hi {{first_name}}", "body": "Hello from {{company}}"},
            {"delay_days": 3, "subject": "Following up", "body": "Second"},
        ],
    )
    enrolled = auth_client.post(
        f"/api/v1/sequences/{created['id']}/enroll", json={"contact_id": contact["id"]}
    )
    assert enrolled.status_code == 201, enrolled.text

    outcome = auth_client.post("/api/v1/sequences/dispatch").json()
    assert outcome["sent"] == 1
    assert outcome["completed"] == 0

    # The provider got the rendered message, not the template.
    assert len(provider) == 1
    assert provider[0]["to"] == contact["email"]
    assert provider[0]["subject"] == "Hi Ishita"
    assert provider[0]["text"] == "Hello from Acme"

    progressed = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"][
        0
    ]
    assert progressed["current_step"] == 1
    assert progressed["status"] == "active"
    assert progressed["last_sent_at"] is not None
    assert progressed["next_send_at"] is not None
    # The second step is three days out, not now.
    assert progressed["next_send_at"][:10] > progressed["last_sent_at"][:10]

    # The send is on the contact's email timeline like any other message.
    timeline = auth_client.get("/api/v1/email/messages", params={"contact_id": contact["id"]}).json()["items"]
    assert any(item["subject"] == "Hi Ishita" for item in timeline)


def test_dispatch_only_touches_steps_that_are_due(auth_client, configured_email, provider):
    _due_enrollment(
        auth_client,
        [
            {"delay_days": 0, "subject": "First", "body": "First"},
            {"delay_days": 30, "subject": "Second", "body": "Second"},
        ],
    )

    assert auth_client.post("/api/v1/sequences/dispatch").json()["sent"] == 1
    # Step two is a month away: a second poll must do nothing at all.
    assert auth_client.post("/api/v1/sequences/dispatch").json() == {
        "sent": 0,
        "failed": 0,
        "completed": 0,
        "checked": 0,
    }
    assert len(provider) == 1


def test_dispatch_completes_the_enrollment_on_the_last_step(auth_client, configured_email, provider):
    _, contact, _ = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Only", "body": "Body"}])

    assert auth_client.post("/api/v1/sequences/dispatch").json()["completed"] == 1
    progressed = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"][
        0
    ]
    assert progressed["status"] == "completed"
    assert progressed["next_send_at"] is None


def test_dispatch_skips_a_paused_sequence(auth_client, configured_email, provider):
    created, contact, _ = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])

    auth_client.patch(f"/api/v1/sequences/{created['id']}", json={"is_active": False})
    assert auth_client.post("/api/v1/sequences/dispatch").json()["sent"] == 0
    assert provider == []


def test_dispatch_fails_an_enrollment_whose_contact_lost_their_email(auth_client, configured_email, provider):
    _, contact, _ = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    run_sql("UPDATE contacts SET email = NULL WHERE id = :id", {"id": contact["id"]})

    outcome = auth_client.post("/api/v1/sequences/dispatch").json()
    assert outcome["failed"] == 1
    progressed = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"][
        0
    ]
    assert progressed["status"] == "failed"
    assert "email" in progressed["last_error"].lower()
    assert provider == []


def test_dispatch_fails_when_the_provider_refuses(auth_client, configured_email, monkeypatch):
    async def refuse(config, *, to, subject, text, html=None, reply_to=None):
        raise email_module.EmailSendFailed("domain is not verified", status_code=403)

    monkeypatch.setattr(email_module, "send_message", refuse)
    _, contact, _ = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])

    assert auth_client.post("/api/v1/sequences/dispatch").json()["failed"] == 1
    progressed = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"][
        0
    ]
    assert progressed["status"] == "failed"
    assert progressed["last_error"] == "domain is not verified"


def test_dispatch_is_a_noop_without_a_provider(auth_client, monkeypatch):
    monkeypatch.setattr(config_module.settings, "email_provider", "resend")
    monkeypatch.setattr(config_module.settings, "email_api_key", "")
    monkeypatch.setattr(config_module.settings, "email_from", "")
    _, contact, _ = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])

    outcome = auth_client.post("/api/v1/sequences/dispatch").json()
    assert outcome["sent"] == 0
    assert outcome["skipped"] == "not_configured"
    progressed = auth_client.get("/api/v1/sequences/enrollments", params={"contact_id": contact["id"]}).json()["items"][
        0
    ]
    # Nothing moves while email is unconfigured; the step is still owed.
    assert progressed["status"] == "active"
    assert progressed["current_step"] == 0


def test_dispatch_requires_a_session(anonymous_client, configured_email):
    response = anonymous_client.post("/api/v1/sequences/dispatch")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Pause / resume / cancel
# ---------------------------------------------------------------------------


def test_pausing_parks_the_enrollment_and_resuming_reanchors_it(auth_client, configured_email, provider):
    created, contact, enrollment = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])

    paused = auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["next_send_at"] is None

    # A paused contact is not due, whatever the clock says.
    assert auth_client.post("/api/v1/sequences/dispatch").json()["sent"] == 0

    resumed = auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "active"})
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert resumed.json()["next_send_at"] is not None
    assert resumed.json()["current_step"] == 0


def test_cancelling_is_final(auth_client):
    _, _, enrollment = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    cancelled = auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "cancelled"})
    assert cancelled.status_code == 200

    resume = auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "active"})
    assert resume.status_code == 409


def test_pause_rejects_a_completed_enrollment(auth_client, configured_email, provider):
    _, _, enrollment = _due_enrollment(auth_client, [{"delay_days": 0, "subject": "Hi", "body": "Body"}])
    auth_client.post("/api/v1/sequences/dispatch")

    response = auth_client.patch(f"/api/v1/sequences/enrollments/{enrollment['id']}", json={"status": "paused"})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_preview_renders_steps_against_a_real_contact(auth_client):
    created = _create_sequence(
        auth_client,
        steps=[{"delay_days": 0, "subject": "Hi {{first_name}}", "body": "From {{company}}"}],
    )
    contact = _create_contact(auth_client, email="someone@example.com", company_name="Acme")

    body = auth_client.post(f"/api/v1/sequences/{created['id']}/preview", json={"contact_id": contact["id"]}).json()
    assert body["steps"][0]["subject"] == "Hi Ishita"
    assert body["steps"][0]["body"] == "From Acme"
