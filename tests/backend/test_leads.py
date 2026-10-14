"""End-to-end tests for the leads module.

Runs against real PostgreSQL through the HTTP API, so it exercises the
migration, the scoring engine and the conversion transaction together. The
conversion tests matter most: a lead must never produce a duplicate contact or
company, and the lead must retain the trail afterwards.
"""

from __future__ import annotations

from .conftest import run_sql, unique

LEAD_PAYLOAD = {
    "first_name": "Ishita",
    "last_name": "Rao",
    "job_title": "Head of Data",
    "department": "Data",
    "seniority": "Director",
    "email": "ishita.rao@acme-analytics.example.com",
    "email_status": "Verified",
    "phone": "+91 98111 22233",
    "linkedin_url": "https://www.linkedin.com/in/ishita-rao",
    "website": "https://acme-analytics.example.com",
    "company_name": "Acme Analytics",
    "company_domain": "acme-analytics.example.com",
    "industry": "Data Analytics",
    "employee_count": 80,
    "company_size": "51-200",
    "city": "Hyderabad",
    "state": "Telangana",
    "country": "India",
    "lead_source": "Conference",
    "campaign": "Q4 Data Summit",
    "priority": "High",
    "notes": "Met at the Q4 data summit.",
}


def promote_to_superuser(email: str) -> None:
    run_sql("UPDATE users SET is_superuser = true WHERE email = :email", {"email": email})


def _create_lead(auth_client, **overrides):
    payload = {**LEAD_PAYLOAD, **overrides}
    response = auth_client.post("/api/v1/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_lead_round_trips_every_field(auth_client):
    body = _create_lead(auth_client)

    assert body["first_name"] == "Ishita"
    assert body["last_name"] == "Rao"
    assert body["job_title"] == "Head of Data"
    assert body["email"] == LEAD_PAYLOAD["email"]
    assert body["phone"] == "+919811122233"  # normalised display form
    assert body["linkedin_url"] == LEAD_PAYLOAD["linkedin_url"]
    assert body["website"] == LEAD_PAYLOAD["website"]
    assert body["company_name"] == "Acme Analytics"
    assert body["company_domain"] == "acme-analytics.example.com"
    assert body["industry"] == "Data Analytics"
    assert body["employee_count"] == 80
    assert body["city"] == "Hyderabad"
    assert body["state"] == "Telangana"
    assert body["country"] == "India"
    assert body["lead_source"] == "Conference"
    assert body["campaign"] == "Q4 Data Summit"
    assert body["priority"] == "High"
    assert body["notes"] == LEAD_PAYLOAD["notes"]
    assert body["lifecycle_stage"] == "New"
    assert body["lead_status"] == "New"
    assert body["display_name"].startswith("Ishita")
    assert body["is_archived"] is False
    assert body["converted_at"] is None


def test_partial_patch_touches_only_the_named_field(auth_client):
    created = _create_lead(auth_client)

    response = auth_client.patch(f"/api/v1/leads/{created['id']}", json={"priority": "Urgent"})
    assert response.status_code == 200, response.text
    updated = response.json()

    assert updated["priority"] == "Urgent"
    assert updated["email"] == created["email"]
    assert updated["company_name"] == created["company_name"]
    assert updated["lifecycle_stage"] == created["lifecycle_stage"]


def test_null_clears_a_field_and_empty_list_clears_tags(auth_client):
    created = _create_lead(auth_client, tags=["warm-lead"])

    response = auth_client.patch(
        f"/api/v1/leads/{created['id']}", json={"notes": None, "campaign": None, "tags": []}
    )
    assert response.status_code == 200, response.text
    cleared = response.json()

    assert cleared["notes"] is None
    assert cleared["campaign"] is None
    assert cleared["tag_names"] == []
    assert cleared["email"] == created["email"]


def test_invalid_enum_values_are_rejected(auth_client):
    assert auth_client.post("/api/v1/leads", json={**LEAD_PAYLOAD, "lifecycle_stage": "Bogus"}).status_code == 422
    assert auth_client.post("/api/v1/leads", json={**LEAD_PAYLOAD, "priority": "Whenever"}).status_code == 422
    # "Converted" is reserved for the convert endpoint.
    assert auth_client.post("/api/v1/leads", json={**LEAD_PAYLOAD, "lead_status": "Converted"}).status_code == 422


def test_unknown_lead_is_a_404(auth_client):
    assert auth_client.get("/api/v1/leads/99999999").status_code == 404
    assert auth_client.patch("/api/v1/leads/99999999", json={"priority": "Low"}).status_code == 404
    assert auth_client.post("/api/v1/leads/99999999/convert", json={}).status_code == 404
    assert auth_client.delete("/api/v1/leads/99999999").status_code == 404


def test_archive_restore_and_delete(auth_client):
    created = _create_lead(auth_client)
    lead_id = created["id"]

    assert auth_client.post(f"/api/v1/leads/{lead_id}/archive").json()["is_archived"] is True
    # Archived leads are excluded from the default listing.
    default_ids = [item["id"] for item in auth_client.get("/api/v1/leads").json()["items"]]
    assert lead_id not in default_ids
    archived_ids = [item["id"] for item in auth_client.get("/api/v1/leads", params={"archived": True}).json()["items"]]
    assert lead_id in archived_ids

    assert auth_client.post(f"/api/v1/leads/{lead_id}/restore").json()["is_archived"] is False
    assert auth_client.delete(f"/api/v1/leads/{lead_id}").status_code == 204
    assert auth_client.get(f"/api/v1/leads/{lead_id}").status_code == 404


def test_leads_require_authentication(anonymous_client):
    assert anonymous_client.get("/api/v1/leads").status_code in (401, 403)
    assert anonymous_client.post("/api/v1/leads", json=LEAD_PAYLOAD).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Search, filters, export
# ---------------------------------------------------------------------------


def test_search_and_filtering(auth_client):
    token = unique("lead")
    created = _create_lead(auth_client, email=f"{token}@example.com", full_name=f"{token} Prospect")

    found = auth_client.get("/api/v1/leads", params={"q": token})
    assert found.status_code == 200, found.text
    assert created["id"] in [item["id"] for item in found.json()["items"]]

    by_status = auth_client.get("/api/v1/leads", params={"lead_status": "New"})
    assert by_status.status_code == 200
    assert created["id"] in [item["id"] for item in by_status.json()["items"]]

    by_source = auth_client.get("/api/v1/leads", params={"lead_source": "Conference"})
    assert created["id"] in [item["id"] for item in by_source.json()["items"]]

    by_tags = auth_client.get("/api/v1/leads", params={"tags": "no-such-tag-anywhere"})
    assert by_tags.json()["total"] == 0


def test_overdue_follow_up_filter(auth_client):
    import datetime

    past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2)).isoformat()
    future = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=2)).isoformat()
    overdue = _create_lead(auth_client, email=f"{unique('od')}@example.com", next_follow_up_at=past)
    upcoming = _create_lead(auth_client, email=f"{unique('up')}@example.com", next_follow_up_at=future)

    result = auth_client.get("/api/v1/leads", params={"overdue_follow_up": True})
    assert result.status_code == 200, result.text
    ids = [item["id"] for item in result.json()["items"]]
    assert overdue["id"] in ids
    assert upcoming["id"] not in ids


def test_export_returns_rows_with_score_summary(auth_client):
    token = unique("exp")
    _create_lead(auth_client, email=f"{token}@example.com", full_name=f"{token} Exported")

    response = auth_client.get("/api/v1/leads/export", params={"q": token})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    row = body["rows"][0]
    assert row["email"] == f"{token}@example.com"
    assert row["lead_score"] > 0
    assert row["score_summary"]


def test_bulk_tag(auth_client):
    first = _create_lead(auth_client, email=f"{unique('bt')}@example.com")
    second = _create_lead(auth_client, email=f"{unique('bt')}@example.com")

    response = auth_client.post(
        "/api/v1/leads/bulk-tag",
        json={"lead_ids": [first["id"], second["id"]], "tags": ["bulk-tagged"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 2

    listed = auth_client.get(f"/api/v1/leads/{first['id']}")
    assert listed.json()["tag_names"] == ["bulk-tagged"]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_is_explainable_and_reflects_missing_data(auth_client):
    rich = _create_lead(auth_client)
    sparse = _create_lead(auth_client, email=None, phone=None, job_title=None, seniority=None)

    assert rich["lead_score"] > sparse["lead_score"]
    assert rich["fit_score"] > 0
    breakdown = {rule["key"]: rule for rule in rich["score_breakdown"]}
    assert breakdown["business_email"]["earned"] is True
    assert breakdown["decision_maker"]["earned"] is True
    assert breakdown["geography_fit"]["earned"] is True
    # No integration has logged anything, so engagement is honestly zero.
    assert rich["engagement_score"] == 0
    assert breakdown["logged_interaction"]["earned"] is False


def test_free_email_scores_below_business_email(auth_client):
    business = _create_lead(auth_client, email=f"{unique('biz')}@acme-corp.example.com")
    free = _create_lead(auth_client, email=f"{unique('free')}@gmail.com")

    business_rules = {rule["key"]: rule["earned"] for rule in business["score_breakdown"]}
    free_rules = {rule["key"]: rule["earned"] for rule in free["score_breakdown"]}
    assert business_rules["business_email"] is True
    assert free_rules["business_email"] is False
    assert business["lead_score"] > free["lead_score"]


def test_logged_activity_raises_engagement_score(auth_client, signed_up):
    client, user = signed_up
    promote_to_superuser(user["email"])
    user_id = run_sql("SELECT id FROM users WHERE email = :email", {"email": user["email"]})[0]["id"]
    lead = _create_lead(client)
    assert lead["engagement_score"] == 0

    before = lead["score_breakdown"]
    # A real activity row for this lead is what the engagement half reads.
    run_sql(
        "INSERT INTO activity_logs (user_id, action, entity_type, entity_id, description, _metadata)"
        " VALUES (:uid, 'lead_called', 'leads', :lid, 'Called the prospect', '{}'::jsonb)",
        {"uid": user_id, "lid": lead["id"]},
    )

    rescored = client.post(f"/api/v1/leads/{lead['id']}/rescore")
    assert rescored.status_code == 200, rescored.text
    body = rescored.json()
    assert body["engagement_score"] == 100
    assert body["lead_score"] > lead["lead_score"]
    earned = {rule["key"] for rule in body["score_breakdown"] if rule["earned"]}
    assert "logged_interaction" in earned
    assert len(before) == len(body["score_breakdown"])


def test_patch_rescores_when_a_scored_field_changes(auth_client):
    lead = _create_lead(auth_client, email=None)
    low = lead["lead_score"]

    updated = auth_client.patch(f"/api/v1/leads/{lead['id']}", json={"email": "now@business-domain.example.com"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["lead_score"] > low


def test_scoring_rules_are_readable_and_admin_only_to_change(auth_client, signed_up):
    client, user = signed_up

    # Any signed-in user can read the active configuration.
    read = client.get("/api/v1/leads/scoring-rules")
    assert read.status_code == 200, read.text
    assert "business_email" in read.json()["weights"]

    # A regular user cannot change it.
    denied = client.put("/api/v1/leads/scoring-rules", json={"weights": {"business_email": 40}})
    assert denied.status_code == 403

    promote_to_superuser(user["email"])
    allowed = client.put("/api/v1/leads/scoring-rules", json={"weights": {"business_email": 40}})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["weights"]["business_email"] == 40

    # Unknown rules and malformed values are rejected rather than ignored.
    assert client.put("/api/v1/leads/scoring-rules", json={"weights": {"nonsense": 5}}).status_code == 400
    assert client.put("/api/v1/leads/scoring-rules", json={"weights": {"business_email": -1}}).status_code == 400
    assert client.put("/api/v1/leads/scoring-rules", json={"unexpected": 1}).status_code == 400


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def test_convert_creates_contact_and_company(auth_client):
    lead = _create_lead(auth_client)

    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["created_contact"] is True
    assert body["created_company"] is True
    assert body["contact"]["email"] == lead["email"]
    assert body["contact"]["job_title"] == "Head of Data"
    assert body["contact"]["company_id"] == body["company"]["id"]
    assert body["company"]["name"] == "Acme Analytics"
    assert body["company"]["employee_count"] == 80
    assert body["company"]["industry"] == "Data Analytics"

    # The lead keeps the trail rather than being deleted.
    assert body["lead"]["lead_status"] == "Converted"
    assert body["lead"]["lifecycle_stage"] == "Converted"
    assert body["lead"]["converted_contact_id"] == body["contact"]["id"]
    assert body["lead"]["converted_company_id"] == body["company"]["id"]
    assert body["lead"]["converted_at"] is not None

    # The contact is a real, listable record.
    listed = auth_client.get(f"/api/v1/contacts/{body['contact']['id']}")
    assert listed.status_code == 200
    assert listed.json()["email"] == lead["email"]


def test_convert_twice_is_refused(auth_client):
    lead = _create_lead(auth_client)
    first = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert first.status_code == 200

    second = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert second.status_code == 409
    assert "already converted" in second.json()["detail"]


def test_convert_links_existing_contact_instead_of_duplicating(auth_client):
    email = f"{unique('dup')}@example.com"
    existing_contact = auth_client.post(
        "/api/v1/contacts", json={"first_name": "Existing", "email": email}
    ).json()

    lead = _create_lead(auth_client, email=email)
    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["created_contact"] is False
    assert body["contact"]["id"] == existing_contact["id"]

    # Exactly one contact exists for that email.
    count = run_sql("SELECT count(*) AS n FROM contacts WHERE lower(email) = :email", {"email": email})[0]["n"]
    assert count == 1


def test_convert_create_mode_refuses_when_a_match_exists(auth_client):
    email = f"{unique('strict')}@example.com"
    auth_client.post("/api/v1/contacts", json={"first_name": "Existing", "email": email})
    lead = _create_lead(auth_client, email=email)

    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={"contact_mode": "create"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_convert_link_mode_requires_a_match(auth_client):
    lead = _create_lead(auth_client, email=f"{unique('nomatch')}@example.com")

    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={"contact_mode": "link"})
    assert response.status_code == 404

    # Nothing was created by the failed attempt.
    assert auth_client.get(f"/api/v1/leads/{lead['id']}").json()["converted_at"] is None


def test_convert_can_skip_the_company(auth_client):
    lead = _create_lead(auth_client)
    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={"company_mode": "none"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["company"] is None
    assert body["contact"]["company_id"] is None
    assert body["lead"]["converted_company_id"] is None


def test_convert_does_not_overwrite_existing_contact_data(auth_client):
    email = f"{unique('keep')}@example.com"
    existing = auth_client.post(
        "/api/v1/contacts", json={"first_name": "Curated", "job_title": "CTO", "email": email}
    ).json()

    lead = _create_lead(auth_client, email=email, job_title="Intern", first_name="Lead First Name")
    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert response.status_code == 200, response.text
    contact = response.json()["contact"]

    assert contact["id"] == existing["id"]
    # Curated values survive; only blanks are filled.
    assert contact["first_name"] == "Curated"
    assert contact["job_title"] == "CTO"
    assert contact["company_id"] is not None


def test_convert_applies_the_requested_contact_stage(auth_client):
    lead = _create_lead(auth_client, email=f"{unique('stage')}@example.com")
    response = auth_client.post(
        f"/api/v1/leads/{lead['id']}/convert", json={"contact_stage": "Qualified"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["contact"]["stage"] == "Qualified"

    # An unknown stage is rejected on a lead that has not been converted yet.
    fresh = _create_lead(auth_client, email=f"{unique('stage')}@example.com")
    bad = auth_client.post(f"/api/v1/leads/{fresh['id']}/convert", json={"contact_stage": "Nonsense"})
    assert bad.status_code == 422


def test_archived_lead_must_be_restored_before_converting(auth_client):
    lead = _create_lead(auth_client)
    auth_client.post(f"/api/v1/leads/{lead['id']}/archive")

    response = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={})
    assert response.status_code == 409
    assert "Restore" in response.json()["detail"]


def test_conversion_records_activity_and_audit(auth_client):
    lead = _create_lead(auth_client)
    body = auth_client.post(f"/api/v1/leads/{lead['id']}/convert", json={}).json()

    rows = run_sql(
        "SELECT action FROM activity_logs WHERE entity_type = 'leads' AND entity_id = :lid",
        {"lid": lead["id"]},
    )
    actions = {row["action"] for row in rows}
    assert "lead_converted" in actions

    audits = run_sql(
        "SELECT action FROM audit_logs WHERE entity_type = 'lead' AND entity_id = :lid",
        {"lid": lead["id"]},
    )
    assert "convert" in {row["action"] for row in audits}

    # The new contact also gets an activity entry pointing at the lead.
    contact_activity = run_sql(
        "SELECT action FROM activity_logs WHERE entity_type = 'contacts' AND entity_id = :cid",
        {"cid": body["contact"]["id"]},
    )
    assert contact_activity


# ---------------------------------------------------------------------------
# Global search integration
# ---------------------------------------------------------------------------


def test_global_search_includes_leads(auth_client):
    token = unique("gl")
    lead = _create_lead(auth_client, full_name=f"{token} Searchable", email=f"{token}@example.com")

    response = auth_client.get("/api/v1/search/global", params={"q": token, "entity": "leads"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert lead["id"] in [item["id"] for item in body["leads"]]

    all_results = auth_client.get("/api/v1/search/global", params={"q": token})
    assert all_results.json()["total"] >= 1
