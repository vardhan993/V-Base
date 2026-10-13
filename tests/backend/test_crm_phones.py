"""CRM pipeline, follow-up tasks, phone country codes, import custom fields."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Phone normalization unit tests (no database)
# ---------------------------------------------------------------------------


def test_normalize_phone_keeps_country_code():
    from nexus.core.phones import normalize_phone

    parsed = normalize_phone("+1 (415) 555-0132")
    assert parsed is not None
    assert parsed.display == "+14155550132"
    assert parsed.e164 == "+14155550132"
    assert parsed.has_country_code is True
    assert parsed.suspicious is False


def test_normalize_phone_converts_00_prefix():
    from nexus.core.phones import normalize_phone

    parsed = normalize_phone("0044 20 7946 0958")
    assert parsed is not None
    assert parsed.display == "+442079460958"
    assert parsed.has_country_code is True


def test_normalize_phone_flags_local_numbers():
    from nexus.core.phones import normalize_phone

    parsed = normalize_phone("98765 43210")
    assert parsed is not None
    assert parsed.display == "9876543210"
    assert parsed.e164 is None
    assert parsed.has_country_code is False


def test_normalize_phone_edge_cases():
    from nexus.core.phones import canonical_for_matching, normalize_phone

    assert normalize_phone(None) is None
    assert normalize_phone("   ") is None
    assert normalize_phone("n/a") is None
    assert normalize_phone("+1-800-555-0100 x123") is not None
    assert normalize_phone("+1-800-555-0100 x123").display == "+18005550100"
    assert normalize_phone("123").suspicious is True
    assert normalize_phone("+" + "1" * 16).suspicious is True
    # Same number in different wrappings matches; local never equals intl.
    assert canonical_for_matching("+1 (415) 555-0132") == "+14155550132"
    assert canonical_for_matching("+14155550132") == "+14155550132"
    assert canonical_for_matching("4155550132") == "4155550132"
    assert canonical_for_matching("+14155550132") != canonical_for_matching("4155550132")


# ---------------------------------------------------------------------------
# Contacts: stage + phone normalization through the API
# ---------------------------------------------------------------------------


def test_create_contact_normalizes_phone_and_defaults_stage(auth_client):
    from .conftest import unique as _unique

    token = _unique("phone")
    response = auth_client.post(
        "/api/v1/contacts",
        json={"full_name": "Phone Test", "email": f"{token}@example.com", "phone": "+91 98765 43210"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["phone"] == "+919876543210"
    assert body["stage"] == "New"


def test_create_contact_rejects_unknown_stage(auth_client):
    response = auth_client.post("/api/v1/contacts", json={"full_name": "Stage Test", "stage": "Won"})
    assert response.status_code == 422


def test_stage_filter_and_update(auth_client):
    created = auth_client.post("/api/v1/contacts", json={"full_name": "Funnel Test", "stage": "Qualified"})
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]

    filtered = auth_client.get("/api/v1/contacts", params={"stage": "Qualified"})
    assert filtered.status_code == 200
    assert any(c["id"] == contact_id for c in filtered.json()["items"])

    other = auth_client.get("/api/v1/contacts", params={"stage": "Customer"})
    assert all(c["id"] != contact_id for c in other.json()["items"])

    updated = auth_client.patch(f"/api/v1/contacts/{contact_id}", json={"stage": "Customer"})
    assert updated.status_code == 200
    assert updated.json()["stage"] == "Customer"

    bad = auth_client.patch(f"/api/v1/contacts/{contact_id}", json={"stage": "Nope"})
    assert bad.status_code == 422


# ---------------------------------------------------------------------------
# Follow-up tasks
# ---------------------------------------------------------------------------


def test_tasks_crud_and_summary(auth_client):
    contact = auth_client.post("/api/v1/contacts", json={"full_name": "Task Owner"}).json()

    created = auth_client.post(
        "/api/v1/tasks",
        json={"title": "Call back", "contact_id": contact["id"], "due_at": "2030-01-01T10:00:00Z"},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["contact_name"] == "Task Owner"
    assert created.json()["done"] is False

    listed = auth_client.get("/api/v1/tasks", params={"contact_id": contact["id"]})
    assert any(t["id"] == task_id for t in listed.json()["items"])

    done = auth_client.patch(f"/api/v1/tasks/{task_id}", json={"done": True})
    assert done.status_code == 200
    assert done.json()["done"] is True

    summary = auth_client.get("/api/v1/tasks/summary")
    assert summary.status_code == 200
    assert summary.json()["open"] >= 0

    deleted = auth_client.delete(f"/api/v1/tasks/{task_id}")
    assert deleted.status_code == 204
    assert auth_client.patch(f"/api/v1/tasks/{task_id}", json={"done": False}).status_code == 404


def test_tasks_validation(auth_client):
    assert auth_client.post("/api/v1/tasks", json={"title": "   "}).status_code == 400
    assert auth_client.post("/api/v1/tasks", json={"title": "x", "contact_id": 999999}).status_code == 404
    assert auth_client.post("/api/v1/tasks", json={"title": "x", "due_at": "not-a-date"}).status_code == 400


def test_pipeline_summary_lists_every_stage(auth_client):
    auth_client.post("/api/v1/contacts", json={"full_name": "Pipe Test", "stage": "Proposal"})
    response = auth_client.get("/api/v1/analytics/pipeline")
    assert response.status_code == 200
    body = response.json()
    assert [s["stage"] for s in body["stages"]] == ["New", "Contacted", "Qualified", "Proposal", "Customer", "Lost"]
    assert body["stages"][3]["count"] >= 1
    assert "open_tasks" in body and "overdue_tasks" in body


# ---------------------------------------------------------------------------
# Import: multiple custom-field columns
# ---------------------------------------------------------------------------

CUSTOM_CSV = (
    "Full Name,Email,Mobile,Level,Language\n"
    "Custom Import,custom-import@example.com,+1 415 555 0100,Senior,English\n"
)


def test_import_mapping_rejects_bad_custom_targets(auth_client):
    response = auth_client.post(
        "/api/v1/import/upload", files={"file": ("c.csv", CUSTOM_CSV.encode(), "text/csv")}
    )
    assert response.status_code == 201
    job_id = response.json()["job_id"]
    bad = auth_client.post(
        f"/api/v1/import/mapping/{job_id}", json={"mapping": {"Level": "custom:person:T20"}}
    )
    assert bad.status_code == 400


def test_import_writes_multiple_custom_fields(auth_client):
    upload = auth_client.post(
        "/api/v1/import/upload", files={"file": ("c.csv", CUSTOM_CSV.encode(), "text/csv")}
    )
    job_id = upload.json()["job_id"]
    mapping = {
        "Full Name": "full_name",
        "Email": "email",
        "Mobile": "phone",
        "Level": "custom:contact:Seniority Band",
        "Language": "custom:contact:Preferred Language",
    }
    mapped = auth_client.post(f"/api/v1/import/mapping/{job_id}", json={"mapping": mapping})
    assert mapped.status_code == 200, mapped.text
    run = auth_client.post(f"/api/v1/import/run/{job_id}")
    assert run.status_code == 200, run.text
    assert run.json()["rows_added"] == 1

    contacts = auth_client.get("/api/v1/contacts", params={"email": "custom-import@example.com"}).json()
    assert contacts["total"] == 1
    contact = contacts["items"][0]
    assert contact["phone"] == "+14155550100"

    values = auth_client.get(f"/api/v1/custom-fields/values/contact/{contact['id']}").json()
    assert values.get("seniority_band") == "Senior"
    assert values.get("preferred_language") == "English"

    # Re-running in fill_empty mode must not duplicate or overwrite customs.
    run2 = auth_client.post(f"/api/v1/import/run/{job_id}")
    assert run2.status_code == 200, run2.text
    assert run2.json()["rows_added"] == 0
    values2 = auth_client.get(f"/api/v1/custom-fields/values/contact/{contact['id']}").json()
    assert values2.get("seniority_band") == "Senior"


def test_merge_carries_tasks_to_survivor(auth_client):
    keeper = auth_client.post("/api/v1/contacts", json={"full_name": "Merge Keeper"}).json()
    drop = auth_client.post("/api/v1/contacts", json={"full_name": "Merge Keeper"}).json()
    task = auth_client.post(
        "/api/v1/tasks", json={"title": "Call them", "contact_id": drop["id"]}
    ).json()

    scan = auth_client.post("/api/v1/duplicates/scan")
    assert scan.status_code == 200, scan.text
    candidates = auth_client.get("/api/v1/duplicates", params={"status": "open"}).json()["items"]
    match = [c for c in candidates if {c["record_id"], c["match_id"]} == {keeper["id"], drop["id"]}]
    assert match, "expected an open duplicate candidate for the pair"
    merged = auth_client.post(
        f"/api/v1/duplicates/{match[0]['id']}/merge", json={"keep_record_id": keeper["id"]}
    )
    assert merged.status_code == 200, merged.text

    tasks = auth_client.get("/api/v1/tasks", params={"contact_id": keeper["id"]}).json()
    assert any(t["id"] == task["id"] for t in tasks["items"])
    assert auth_client.get(f"/api/v1/contacts/{drop['id']}").status_code == 404


# ---------------------------------------------------------------------------
# Data quality: country-code awareness
# ---------------------------------------------------------------------------


def test_quality_counts_phones_without_country_code(auth_client):
    auth_client.post("/api/v1/contacts", json={"full_name": "Local Phone", "phone": "020 7946 0000"})
    auth_client.post("/api/v1/contacts", json={"full_name": "Intl Phone", "phone": "+44 20 7946 0000"})
    summary = auth_client.get("/api/v1/quality/summary").json()
    assert summary["contacts"]["phone_missing_country_code"] >= 1

    review = auth_client.get(
        "/api/v1/quality/contacts/needs-review",
        params={"missing_email": False, "missing_phone": False, "missing_linkedin": False,
                "missing_company": False, "invalid_email": False, "low_score": 0, "stale": False,
                "phone_missing_country_code": True},
    )
    assert review.status_code == 200
    assert any(c["name"] == "Local Phone" for c in review.json())
