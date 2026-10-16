"""Tests for the CRM engagement features: calls, notes, timeline,
campaigns (with suppression) and exports/vCards."""

from __future__ import annotations

from .conftest import run_sql, unique

# ---------------------------------------------------------------------------


def _create_company() -> int:
    return int(
        run_sql(
            "INSERT INTO companies (name) VALUES (:name) RETURNING id",
            {"name": unique("Call Target Industries-")},
        )[0]["id"]
    )


def _create_contact(email: str, first: str = "Call", last: str = "Target") -> int:
    """Insert a contact with a primary email row (sync test connection)."""
    company_id = _create_company()
    row = run_sql(
        "INSERT INTO contacts (first_name, last_name, email, email_status, company_id) "
        "VALUES (:first, :last, :email, 'valid', :company_id) RETURNING id",
        {"first": first, "last": last, "email": email, "company_id": company_id},
    )
    contact_id = int(row[0]["id"])
    run_sql(
        "INSERT INTO contact_emails (contact_id, email, is_primary, status) VALUES (:cid, :email, true, 'valid')",
        {"cid": contact_id, "email": email},
    )
    return contact_id


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def test_call_crud_round_trip(auth_client):
    email = f"{unique('call')}@example.com"
    contact_id = _create_contact(email)
    headers = {"X-Contact-Check": "1"}

    resp = auth_client.post(
        "/api/v1/calls",
        json={
            "contact_id": contact_id,
            "direction": "outbound",
            "outcome": "connected",
            "duration_seconds": 420,
            "phone_number": "+1 555 0100",
            "notes": "Discussed pricing",
        },
    )
    assert resp.status_code == 201, resp.text
    call = resp.json()
    assert call["outcome"] == "connected"
    assert call["contact_name"] == "Call Target"

    # Filter by contact
    resp = auth_client.get(f"/api/v1/calls?contact_id={contact_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == call["id"]
    assert data["outcome_counts"].get("connected") == 1

    # Update
    resp = auth_client.patch(
        f"/api/v1/calls/{call['id']}",
        json={"outcome": "voicemail", "notes": "Left message"},
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "voicemail"

    # Invalid outcome rejected
    resp = auth_client.patch(f"/api/v1/calls/{call['id']}", json={"outcome": "nonsense"})
    assert resp.status_code == 400

    # Delete
    resp = auth_client.delete(f"/api/v1/calls/{call['id']}")
    assert resp.status_code == 204
    resp = auth_client.get(f"/api/v1/calls?contact_id={contact_id}")
    assert resp.json()["total"] == 0


def test_call_requires_valid_parent(auth_client):
    resp = auth_client.post(
        "/api/v1/calls",
        json={"contact_id": 987654, "direction": "inbound", "outcome": "missed"},
    )
    assert resp.status_code == 404

    resp = auth_client.post(
        "/api/v1/calls",
        json={"direction": "inbound", "outcome": "missed"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Notes + timeline
# ---------------------------------------------------------------------------


def test_note_crud_and_timeline(auth_client):
    email = f"{unique('note')}@example.com"
    contact_id = _create_contact(email)

    resp = auth_client.post("/api/v1/notes", json={"contact_id": contact_id, "body": "Met at the SaaS summit"})
    assert resp.status_code == 201, resp.text
    note = resp.json()
    assert note["author"] is not None

    resp = auth_client.post(
        "/api/v1/calls",
        json={"contact_id": contact_id, "direction": "inbound", "outcome": "connected", "duration_seconds": 90},
    )
    assert resp.status_code == 201

    # Timeline merges both entry types
    resp = auth_client.get(f"/api/v1/timeline?contact_id={contact_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    kinds = [i["kind"] for i in items]
    assert set(kinds) == {"call", "note"}
    assert len(items) == 2

    # Pin the note to the top
    resp = auth_client.patch(f"/api/v1/notes/{note['id']}", json={"pinned": True})
    assert resp.status_code == 200
    assert resp.json()["pinned"] is True
    resp = auth_client.get(f"/api/v1/notes?contact_id={contact_id}")
    assert resp.json()["items"][0]["pinned"] is True

    # Delete
    resp = auth_client.delete(f"/api/v1/notes/{note['id']}")
    assert resp.status_code == 204


def test_note_requires_exactly_one_parent(auth_client):
    resp = auth_client.post("/api/v1/notes", json={"body": "orphan"})
    assert resp.status_code == 400

    contact_id = _create_contact(f"{unique('twop')}@example.com")
    company_id = run_sql("SELECT company_id FROM contacts WHERE id = :id", {"id": contact_id})[0]["company_id"]
    resp = auth_client.post(
        "/api/v1/notes",
        json={"body": "two parents", "contact_id": contact_id, "company_id": company_id},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


def _make_list_with_contacts(emails: list[str]) -> int:
    list_name = unique("campaign-list")
    run_sql("INSERT INTO lists (name) VALUES (:name)", {"name": list_name})
    list_id = int(
        run_sql("SELECT id FROM lists WHERE name = :name", {"name": list_name})[0]["id"]
    )
    for i, addr in enumerate(emails):
        contact_id = _create_contact(email=addr, first=f"C{i}", last="Lister")
        run_sql(
            "INSERT INTO list_contacts (list_id, contact_id) VALUES (:lid, :cid)",
            {"lid": list_id, "cid": contact_id},
        )
    return list_id


def test_campaign_create_suppresses_and_requires_list(auth_client):
    resp = auth_client.post("/api/v1/campaigns", json={"name": "no list", "subject": "s", "body": "b"})
    assert resp.status_code == 400

    list_id = _make_list_with_contacts(["good1@example.com", "good2@example.com"])
    resp = auth_client.post(
        "/api/v1/campaigns",
        json={"name": "Launch blast", "subject": "We shipped", "body": "Check it out", "list_id": list_id},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["counts"].get("pending") == 2


def test_campaign_suppression_flags_unsubscribed(auth_client):
    list_name = unique("suppress-list")
    run_sql("INSERT INTO lists (name) VALUES (:name)", {"name": list_name})
    list_id = int(run_sql("SELECT id FROM lists WHERE name = :name", {"name": list_name})[0]["id"])

    # Contacts created with raw SQL so exactly ONE email row exists each.
    ok_email = f"{unique('keep')}@example.com"
    gone_email = f"{unique('gone')}@example.com"
    company_id = _create_company()
    ok_id = int(
        run_sql(
            "INSERT INTO contacts (first_name, last_name, email, email_status, company_id) VALUES ('Ok','Guy',:email,'valid',:cid) RETURNING id",
            {"email": ok_email, "cid": company_id},
        )[0]["id"]
    )
    gone_id = int(
        run_sql(
            "INSERT INTO contacts (first_name, last_name, email, email_status, company_id) VALUES ('Gone','Guy',:email,'valid',:cid) RETURNING id",
            {"email": gone_email, "cid": company_id},
        )[0]["id"]
    )
    # Ok: primary email valid -> stays pending. Gone: unsubscribed -> suppressed.
    run_sql(
        "INSERT INTO contact_emails (contact_id, email, is_primary, status) VALUES (:cid, :email, true, 'valid')",
        {"cid": ok_id, "email": ok_email},
    )
    run_sql(
        "INSERT INTO contact_emails (contact_id, email, is_primary, status) VALUES (:cid, :email, true, 'unsubscribed')",
        {"cid": gone_id, "email": gone_email},
    )
    run_sql("INSERT INTO list_contacts (list_id, contact_id) VALUES (:lid, :cid)", {"lid": list_id, "cid": ok_id})
    run_sql("INSERT INTO list_contacts (list_id, contact_id) VALUES (:lid, :cid)", {"lid": list_id, "cid": gone_id})

    resp = auth_client.post(
        "/api/v1/campaigns",
        json={"name": "Suppress test", "subject": "s", "body": "b", "list_id": list_id},
    )
    assert resp.status_code == 201
    counts = resp.json()["counts"]
    assert counts.get("pending") == 1, counts
    assert counts.get("suppressed") == 1, counts


# ---------------------------------------------------------------------------
# Exports and vCard
# ---------------------------------------------------------------------------


def test_export_csv_xlsx_and_vcard(auth_client):
    email = f"{unique('export')}@example.com"
    contact_id = _create_contact(email)

    resp = auth_client.get(f"/api/v1/exports/contacts?ids={contact_id}&format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    assert "full_name" in body
    assert "Call Target" in body

    resp = auth_client.get(f"/api/v1/exports/contacts?ids={contact_id}&format=xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]

    resp = auth_client.get(f"/api/v1/contacts/{contact_id}/vcard")
    assert resp.status_code == 200
    payload = resp.text
    assert payload.startswith("BEGIN:VCARD")
    assert "FN:Call Target" in payload
    assert f"EMAIL;TYPE=INTERNET:{email}" in payload
    assert payload.rstrip().endswith("END:VCARD")


def test_vcard_escapes_commas(auth_client):
    contact_id = _create_contact(
        email=f"{unique('esc')}@example.com", first="Ann, the", last="Trader; Jr"
    )

    resp = auth_client.get(f"/api/v1/contacts/{contact_id}/vcard")
    assert resp.status_code == 200
    assert "FN:Ann\\, the Trader\\; Jr" in resp.text
