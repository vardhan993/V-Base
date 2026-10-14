"""Full create / edit / delete coverage for the contacts and companies CRM
entities, exercised through the real HTTP API against PostgreSQL.

These tests pin the behaviour the record editors depend on: every column is
writable on create, a partial PATCH touches only the fields it names, a null
clears a field, tags round-trip, and deleting removes the record.
"""

from __future__ import annotations

from .conftest import unique

CONTACT_FULL_PAYLOAD = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "full_name": "Ada Lovelace",
    "job_title": "VP Engineering",
    "department": "Engineering",
    "seniority": "VP",
    "email": "ada@example.com",
    "email_status": "Verified",
    "phone": "+91 98765 43210",
    "phone_status": "Verified",
    "stage": "Qualified",
    "linkedin_url": "https://www.linkedin.com/in/ada",
    "company_name": "Analytical Engines",
    "city": "Hyderabad",
    "country": "India",
    "skills": ["Python", "PostgreSQL"],
    "employment_history": [
        {"company_name": "Analytical Engines", "job_title": "VP Engineering", "start_date": "2020"}
    ],
    "source": "Manual",
    "notes": "Met at a conference.",
}

COMPANY_FULL_PAYLOAD = {
    "name": "Analytical Engines",
    "website": "https://analytical.example.com",
    "domain": "analytical.example.com",
    "linkedin_url": "https://www.linkedin.com/company/analytical",
    "industry": "SaaS",
    "sub_industry": "Developer tooling",
    "employee_count": 120,
    "company_size": "51-200",
    "country": "India",
    "state": "Telangana",
    "city": "Hyderabad",
    "headquarters": "Hyderabad, India",
    "founded_year": 2019,
    "technologies": ["Python", "PostgreSQL"],
    "funding_stage": "Series A",
    "company_status": "Active",
    "source": "Manual",
    "notes": "Design partner.",
}


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


def test_create_contact_writes_every_field(auth_client):
    response = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD)
    assert response.status_code == 201, response.text
    body = response.json()

    for key, value in CONTACT_FULL_PAYLOAD.items():
        if key == "phone":
            # The API normalizes phones to a canonical display form.
            assert body["phone"] == "+919876543210"
        else:
            assert body[key] == value, key

    assert body["display_name"] == "Ada Lovelace"
    assert body["data_quality_score"] > 0
    assert body["is_archived"] is False


def test_patch_touches_only_the_named_field(auth_client):
    created = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).json()
    contact_id = created["id"]

    response = auth_client.patch(f"/api/v1/contacts/{contact_id}", json={"job_title": "CTO"})
    assert response.status_code == 200, response.text
    updated = response.json()

    assert updated["job_title"] == "CTO"
    # Everything else is untouched.
    assert updated["email"] == created["email"]
    assert updated["city"] == created["city"]
    assert updated["stage"] == created["stage"]
    assert updated["skills"] == created["skills"]


def test_patch_null_clears_a_field(auth_client):
    created = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).json()

    response = auth_client.patch(f"/api/v1/contacts/{created['id']}", json={"notes": None, "department": None})
    assert response.status_code == 200, response.text
    cleared = response.json()

    assert cleared["notes"] is None
    assert cleared["department"] is None
    assert cleared["email"] == created["email"]


def test_patch_empty_lists_clear_list_columns(auth_client):
    created = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).json()

    response = auth_client.patch(
        f"/api/v1/contacts/{created['id']}", json={"skills": [], "employment_history": []}
    )
    assert response.status_code == 200, response.text
    assert response.json()["skills"] == []
    assert response.json()["employment_history"] == []


def test_tags_round_trip_on_a_contact(auth_client):
    created = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).json()

    tagged = auth_client.patch(
        f"/api/v1/contacts/{created['id']}", json={"tags": ["enterprise", "warm"]}
    )
    assert tagged.status_code == 200, tagged.text
    assert sorted(tagged.json()["tag_names"]) == ["enterprise", "warm"]

    # Replacing the tag set removes the ones no longer listed.
    retagged = auth_client.patch(f"/api/v1/contacts/{created['id']}", json={"tags": ["enterprise"]})
    assert retagged.status_code == 200, retagged.text
    assert retagged.json()["tag_names"] == ["enterprise"]


def test_unknown_stage_is_rejected(auth_client):
    response = auth_client.post("/api/v1/contacts", json={**CONTACT_FULL_PAYLOAD, "stage": "Nonsense"})
    assert response.status_code == 422


def test_invalid_contact_id_is_a_404(auth_client):
    assert auth_client.get("/api/v1/contacts/99999999").status_code == 404
    assert auth_client.patch("/api/v1/contacts/99999999", json={"job_title": "x"}).status_code == 404
    assert auth_client.delete("/api/v1/contacts/99999999").status_code == 404


def test_archive_restore_and_delete_contact(auth_client):
    created = auth_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).json()
    contact_id = created["id"]

    archived = auth_client.post(f"/api/v1/contacts/{contact_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    restored = auth_client.post(f"/api/v1/contacts/{contact_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False

    assert auth_client.delete(f"/api/v1/contacts/{contact_id}").status_code == 204
    assert auth_client.get(f"/api/v1/contacts/{contact_id}").status_code == 404


def test_contact_links_to_company_and_unlinks_when_name_changes(auth_client):
    company = auth_client.post("/api/v1/companies", json=COMPANY_FULL_PAYLOAD).json()

    contact = auth_client.post(
        "/api/v1/contacts",
        json={**CONTACT_FULL_PAYLOAD, "company_name": company["name"]},
    ).json()
    assert contact["company_id"] == company["id"]

    linked = auth_client.get(f"/api/v1/contacts/{contact['id']}/company")
    assert linked.status_code == 200
    assert linked.json()["id"] == company["id"]

    # Renaming to something that matches no company must not leave the record
    # pointing at the previous company.
    renamed = auth_client.patch(
        f"/api/v1/contacts/{contact['id']}", json={"company_name": "Not A Real Company"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["company_id"] is None
    assert renamed.json()["company_name"] == "Not A Real Company"

    # Clearing the name unlinks and leaves the free-text field empty.
    cleared = auth_client.patch(f"/api/v1/contacts/{contact['id']}", json={"company_name": None})
    assert cleared.status_code == 200
    assert cleared.json()["company_id"] is None
    assert cleared.json()["company_name"] is None


# ---------------------------------------------------------------------------
# Companies / accounts
# ---------------------------------------------------------------------------


def test_create_company_writes_every_field(auth_client):
    response = auth_client.post("/api/v1/companies", json=COMPANY_FULL_PAYLOAD)
    assert response.status_code == 201, response.text
    body = response.json()

    for key, value in COMPANY_FULL_PAYLOAD.items():
        assert body[key] == value, key
    assert body["contact_count"] == 0
    assert body["data_quality_score"] > 0


def test_patch_company_touches_only_the_named_field(auth_client):
    created = auth_client.post("/api/v1/companies", json=COMPANY_FULL_PAYLOAD).json()

    response = auth_client.patch(
        f"/api/v1/companies/{created['id']}", json={"employee_count": 500, "company_size": "201-500"}
    )
    assert response.status_code == 200, response.text
    updated = response.json()

    assert updated["employee_count"] == 500
    assert updated["company_size"] == "201-500"
    assert updated["industry"] == created["industry"]
    assert updated["founded_year"] == created["founded_year"]


def test_company_requires_a_name(auth_client):
    assert auth_client.post("/api/v1/companies", json={"industry": "SaaS"}).status_code == 422


def test_company_tags_and_archive_restore_delete(auth_client):
    created = auth_client.post("/api/v1/companies", json=COMPANY_FULL_PAYLOAD).json()
    company_id = created["id"]

    tagged = auth_client.patch(f"/api/v1/companies/{company_id}", json={"tags": ["target"]})
    assert tagged.status_code == 200, tagged.text
    assert tagged.json()["tag_names"] == ["target"]

    assert auth_client.post(f"/api/v1/companies/{company_id}/archive").json()["is_archived"] is True
    assert auth_client.post(f"/api/v1/companies/{company_id}/restore").json()["is_archived"] is False

    assert auth_client.delete(f"/api/v1/companies/{company_id}").status_code == 204
    assert auth_client.get(f"/api/v1/companies/{company_id}").status_code == 404


def test_new_contact_is_searchable_and_listed(auth_client):
    token = unique("crud")
    created = auth_client.post(
        "/api/v1/contacts", json={**CONTACT_FULL_PAYLOAD, "email": f"{token}@example.com"}
    ).json()

    listing = auth_client.get("/api/v1/contacts", params={"q": token})
    assert listing.status_code == 200, listing.text
    ids = [item["id"] for item in listing.json()["items"]]
    assert created["id"] in ids


def test_crud_requires_authentication(anonymous_client):
    assert anonymous_client.get("/api/v1/contacts").status_code in (401, 403)
    assert anonymous_client.post("/api/v1/contacts", json=CONTACT_FULL_PAYLOAD).status_code in (401, 403)
