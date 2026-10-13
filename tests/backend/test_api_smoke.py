"""End-to-end API tests against a real PostgreSQL database."""

from __future__ import annotations

from .conftest import run_sql, unique


def promote_to_superuser(email: str) -> None:
    """Grant the superuser role directly, as an operator would."""
    run_sql("UPDATE users SET is_superuser = true WHERE email = :email", {"email": email})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_reports_app_identity(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "V-Base"


def test_readiness_checks_the_database(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"]["status"] == "ok"
    # A real pooled connection, not a stub.
    assert "pool" in body["database"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_signup_creates_session_and_csrf_cookie(client):
    token = unique("user")
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"{token}@example.com",
            "username": token,
            "password": "Str0ngPassw0rd!",
            "full_name": "Ada Lovelace",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == f"{token}@example.com"
    assert body["csrf_token"]

    # HttpOnly session cookie, readable CSRF cookie.
    assert client.cookies.get("vbase_session")
    assert client.cookies.get("vbase_csrf")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["full_name"] == "Ada Lovelace"
    assert me.json()["session"]["id"] > 0


def test_duplicate_signup_rejected(client):
    token = unique("user")
    payload = {"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"}
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 201
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 409


def test_login_and_logout_round_trip(client):
    token = unique("user")
    payload = {"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"}
    client.post("/api/v1/auth/signup", json=payload)
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200, login.text
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_with_wrong_password_is_401(client):
    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    response = client.post("/api/v1/auth/login", json={"email": f"{token}@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_weak_password_rejected_at_signup(client):
    token = unique("user")
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "short"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Companies and contacts
# ---------------------------------------------------------------------------


def test_company_contact_crud(auth_client):
    c = auth_client.post(
        "/api/v1/companies",
        json={
            "name": "Acme Robotics",
            "domain": "acme.io",
            "industry": "Robotics",
            "city": "Berlin",
            "country": "Germany",
            "employee_count": 120,
            "technologies": ["React", "PostgreSQL"],
        },
    )
    assert c.status_code == 201, c.text
    company = c.json()
    assert company["id"] > 0
    assert company["technologies"] == ["React", "PostgreSQL"]
    assert company["data_quality_score"] > 0

    k = auth_client.post(
        "/api/v1/contacts",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "job_title": "CTO",
            "department": "Engineering",
            "seniority": "C-Level",
            "email": "ada@acme.io",
            "company_id": company["id"],
            "company_name": "Acme Robotics",
        },
    )
    assert k.status_code == 201, k.text
    contact = k.json()
    assert contact["display_name"] == "Ada Lovelace"

    patched = auth_client.patch(f"/api/v1/contacts/{contact['id']}", json={"seniority": "Founder"})
    assert patched.status_code == 200
    assert patched.json()["seniority"] == "Founder"

    got = auth_client.get(f"/api/v1/contacts/{contact['id']}")
    assert got.status_code == 200
    assert got.json()["company_id"] == company["id"]

    assert auth_client.delete(f"/api/v1/contacts/{contact['id']}").status_code in (200, 204)
    assert auth_client.delete(f"/api/v1/companies/{company['id']}").status_code in (200, 204)
    assert auth_client.get(f"/api/v1/companies/{company['id']}").status_code == 404


def test_archive_and_restore_company(auth_client):
    company = auth_client.post("/api/v1/companies", json={"name": unique("Archivable")}).json()
    assert auth_client.post(f"/api/v1/companies/{company['id']}/archive").json()["is_archived"] is True

    default_list = auth_client.get("/api/v1/companies").json()
    assert all(item["id"] != company["id"] for item in default_list["items"])
    archived = auth_client.get("/api/v1/companies", params={"archived": True}).json()
    assert any(item["id"] == company["id"] for item in archived["items"])

    assert auth_client.post(f"/api/v1/companies/{company['id']}/restore").json()["is_archived"] is False


def test_server_side_pagination_and_sorting(auth_client):
    prefix = unique("Paged")
    for index in range(7):
        auth_client.post("/api/v1/companies", json={"name": f"{prefix} {index}"})

    page = auth_client.get("/api/v1/companies", params={"q": prefix, "page": 1, "page_size": 3})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 7
    assert len(body["items"]) == 3
    page2 = auth_client.get("/api/v1/companies", params={"q": prefix, "page": 3, "page_size": 3}).json()
    assert len(page2["items"]) == 1

    ordered = auth_client.get(
        "/api/v1/companies", params={"q": prefix, "sort": "name", "order": "asc", "page_size": 10}
    ).json()
    names = [item["name"] for item in ordered["items"]]
    assert names == sorted(names)


def test_filters_narrow_results(auth_client):
    auth_client.post("/api/v1/companies", json={"name": unique("Filt"), "industry": "Fintech", "country": "France"})
    auth_client.post("/api/v1/companies", json={"name": unique("Filt"), "industry": "Health", "country": "Spain"})

    result = auth_client.get("/api/v1/companies", params={"industry": "Fintech", "country": "France"}).json()
    assert result["total"] >= 1
    assert all(item["industry"] == "Fintech" for item in result["items"])


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_global_search_matches_companies_and_contacts(auth_client):
    company = auth_client.post("/api/v1/companies", json={"name": "Northwind Analytics", "industry": "Data"}).json()
    auth_client.post(
        "/api/v1/contacts",
        json={"full_name": "Grace Hopper", "job_title": "CTO", "email": "grace@northwind.example"},
    )

    by_name = auth_client.get("/api/v1/search/global", params={"q": "northwind"}).json()
    assert any(item["id"] == company["id"] for item in by_name["companies"])

    # Full-text prefix search: "analytic" must find "Analytics".
    by_prefix = auth_client.get("/api/v1/search/global", params={"q": "analytic"}).json()
    assert any(item["id"] == company["id"] for item in by_prefix["companies"])

    by_person = auth_client.get("/api/v1/search/global", params={"q": "grace"}).json()
    assert any("Grace" in item["name"] for item in by_person["contacts"])

    # Trigram similarity tolerates a misspelling (the token need not be a
    # leading prefix, and the fuzzy branch ignores a letter error).
    typo = auth_client.get("/api/v1/search/global", params={"q": "Northwind Analytcs"}).json()
    assert any(item["id"] == company["id"] for item in typo["companies"])

    # Substring search finds text inside a word, which full-text does not:
    # "wind" is not a token of "Northwind", but it is a substring of it.
    substring = auth_client.get("/api/v1/search/global", params={"q": "wind"}).json()
    assert any(item["id"] == company["id"] for item in substring["companies"])


def test_company_list_search_uses_full_text(auth_client):
    created = auth_client.post("/api/v1/companies", json={"name": "Helios Semiconductor", "notes": "chipmaker"}).json()
    found = auth_client.get("/api/v1/companies", params={"q": "semiconductor"}).json()
    assert any(item["id"] == created["id"] for item in found["items"])
    not_found = auth_client.get("/api/v1/companies", params={"q": "nonexistenttermzzz"}).json()
    assert not_found["total"] == 0


def test_search_suggestions_and_recent(auth_client):
    auth_client.post("/api/v1/companies", json={"name": "Suggestion Corp"})
    suggestions = auth_client.get("/api/v1/search/suggestions", params={"q": "Suggest"}).json()
    assert any("Suggestion" in item["name"] for item in suggestions["companies"])

    saved = auth_client.post("/api/v1/search/saved", json={"name": "My search", "query": "suggest"})
    assert saved.status_code == 201, saved.text
    recent = auth_client.get("/api/v1/search/recent").json()
    assert any(item["id"] == saved.json()["id"] for item in recent)
    assert auth_client.delete(f"/api/v1/search/saved/{saved.json()['id']}").status_code == 204


# ---------------------------------------------------------------------------
# Tags, lists, saved views
# ---------------------------------------------------------------------------


def test_tag_list_and_view_workflows(auth_client):
    tag = auth_client.post("/api/v1/tags", json={"name": unique("tag"), "color": "#6366f1"})
    assert tag.status_code == 201, tag.text
    assert any(item["id"] == tag.json()["id"] for item in auth_client.get("/api/v1/tags").json())

    contact_list = auth_client.post("/api/v1/lists", json={"name": unique("list"), "description": "Q1 outreach"})
    assert contact_list.status_code == 201, contact_list.text
    assert any(item["id"] == contact_list.json()["id"] for item in auth_client.get("/api/v1/lists").json())

    view = auth_client.post(
        "/api/v1/views",
        json={"name": "My view", "entity": "contacts", "columns": ["full_name"], "sort": [], "filters": []},
    )
    assert view.status_code == 201, view.text
    view_id = view.json()["id"]

    renamed = auth_client.patch(f"/api/v1/views/{view_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed"

    duplicate = auth_client.post(f"/api/v1/views/{view_id}/duplicate")
    assert duplicate.status_code == 201 and duplicate.json()["id"] != view_id

    listed = auth_client.get("/api/v1/views", params={"entity": "contacts"}).json()
    assert {view_id, duplicate.json()["id"]} <= {item["id"] for item in listed}

    assert auth_client.delete(f"/api/v1/views/{view_id}").status_code in (200, 204)
    assert auth_client.delete(f"/api/v1/views/{duplicate.json()['id']}").status_code in (200, 204)


def test_bulk_tagging(auth_client):
    ids = [auth_client.post("/api/v1/companies", json={"name": unique("Bulk")}).json()["id"] for _ in range(3)]
    response = auth_client.post("/api/v1/companies/bulk-tag", json={"company_ids": ids, "tags": [unique("bulk")]})
    assert response.status_code == 200
    assert response.json()["updated"] == 3


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


def test_custom_field_crud_and_validation(auth_client):
    field = auth_client.post(
        "/api/v1/custom-fields",
        json={
            "entity_type": "contact",
            "name": f"Tier {unique('t')[:6]}",
            "field_type": "single_select",
            "options": ["A", "B"],
        },
    )
    assert field.status_code == 201, field.text
    key = field.json()["key"]

    contact = auth_client.post("/api/v1/contacts", json={"full_name": unique("CF")}).json()

    invalid = auth_client.put(f"/api/v1/custom-fields/values/contact/{contact['id']}", json={"values": {key: "Z"}})
    assert invalid.status_code == 400

    valid = auth_client.put(f"/api/v1/custom-fields/values/contact/{contact['id']}", json={"values": {key: "A"}})
    assert valid.status_code == 200, valid.text

    stored = auth_client.get(f"/api/v1/custom-fields/values/contact/{contact['id']}")
    assert stored.json()[key] == "A"

    duplicate = auth_client.post(
        "/api/v1/custom-fields",
        json={"entity_type": "contact", "name": field.json()["name"], "field_type": "text"},
    )
    assert duplicate.status_code == 409

    assert auth_client.delete(f"/api/v1/custom-fields/{field.json()['id']}").status_code in (200, 204)


# ---------------------------------------------------------------------------
# Analytics, quality, activity
# ---------------------------------------------------------------------------


def test_analytics_reflect_real_rows(auth_client):
    auth_client.post("/api/v1/companies", json={"name": unique("Ana"), "industry": "Fintech"})
    auth_client.post("/api/v1/contacts", json={"full_name": unique("Ana"), "email": "ana@example.com"})

    overview = auth_client.get("/api/v1/analytics/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["companies"] >= 1
    assert body["contacts"] >= 1
    assert body["emails_available"] >= 1

    growth = auth_client.get("/api/v1/analytics/growth", params={"days": 30}).json()
    assert growth["days"] == 30
    assert isinstance(growth["company_series"], list)

    for path in (
        "/api/v1/analytics/companies-by-industry",
        "/api/v1/analytics/companies-by-size",
        "/api/v1/analytics/contacts-by-department",
        "/api/v1/analytics/contacts-by-seniority",
        "/api/v1/analytics/contacts-by-country",
        "/api/v1/analytics/contacts-by-city",
        "/api/v1/analytics/email-coverage",
        "/api/v1/analytics/phone-coverage",
        "/api/v1/analytics/linkedin-coverage",
        "/api/v1/analytics/verification-status",
        "/api/v1/analytics/import-performance",
        "/api/v1/analytics/activity-narrative",
    ):
        response = auth_client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"


def test_quality_summary_and_review_queue(auth_client):
    auth_client.post("/api/v1/contacts", json={"first_name": "Missing", "last_name": "Everything"})
    summary = auth_client.get("/api/v1/quality/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["contacts"]["total"] >= 1
    assert body["contacts"]["missing_phone"] >= 1

    queue = auth_client.get("/api/v1/quality/contacts/needs-review")
    assert queue.status_code == 200
    assert isinstance(queue.json(), list)


def test_activity_log_records_mutations(auth_client):
    auth_client.post("/api/v1/companies", json={"name": unique("Audited")})
    activity = auth_client.get("/api/v1/activity", params={"action": "company_created"})
    assert activity.status_code == 200
    body = activity.json()
    assert body["total"] >= 1
    assert any(item["action"] == "company_created" for item in body["items"])


# ---------------------------------------------------------------------------
# Settings and backup
# ---------------------------------------------------------------------------


def test_settings_app_info_describes_postgres(auth_client):
    info = auth_client.get("/api/v1/settings/app")
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["app_name"] == "V-Base"
    assert body["tagline"] == "Your Business Data. One Powerful Base."
    assert body["database_engine"] == "postgresql"
    assert body["database"]["alembic_revision"] == "0001_initial"
    assert body["database"]["size_bytes"] > 0
    # Credentials must never be exposed.
    assert "password" not in str(body).lower()


def test_preferences_round_trip(auth_client):
    updated = auth_client.patch("/api/v1/settings/preferences", json={"theme": "dark", "density": "compact"})
    assert updated.status_code == 200
    assert updated.json()["theme"] == "dark"

    fetched = auth_client.get("/api/v1/settings/preferences")
    assert fetched.json()["density"] == "compact"


def test_backup_and_restore_round_trip(client):
    token = unique("user")
    email = f"{token}@example.com"
    client.post(
        "/api/v1/auth/signup",
        json={"email": email, "username": token, "password": "Str0ngPassw0rd!"},
    )
    promote_to_superuser(email)
    auth_client = client
    auth_client.post("/api/v1/companies", json={"name": unique("BackedUp")})
    created = auth_client.post("/api/v1/settings/backup")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["size_bytes"] > 0
    assert body["kind"] in {"json", "pg_dump"}

    listed = auth_client.get("/api/v1/settings/backups")
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1
    assert listed.json()["backups"][0]["validation"]["valid"] is True

    # Mutate, then restore and confirm the change is reverted.
    before = auth_client.get("/api/v1/companies").json()["total"]
    auth_client.post("/api/v1/companies", json={"name": unique("AfterBackup")})
    assert auth_client.get("/api/v1/companies").json()["total"] == before + 1

    if body["kind"] == "json":
        restored = auth_client.post("/api/v1/settings/restore", json={"backup_file": body["backup_file"]})
        assert restored.status_code == 200, restored.text
        assert restored.json()["rows_restored"] > 0
        assert auth_client.get("/api/v1/companies").json()["total"] == before


def test_restore_requires_superuser(auth_client):
    """Restore replaces data, so a normal member must not be able to run it."""
    response = auth_client.post("/api/v1/settings/restore", json={"backup_file": "anything.json"})
    assert response.status_code == 403


def test_backup_rejects_path_traversal(client):
    token = unique("user")
    email = f"{token}@example.com"
    client.post(
        "/api/v1/auth/signup",
        json={"email": email, "username": token, "password": "Str0ngPassw0rd!"},
    )
    promote_to_superuser(email)
    response = client.post("/api/v1/settings/restore", json={"backup_file": "../../../etc/passwd"})
    assert response.status_code == 400


def test_export_db_reports_tables_and_command(auth_client):
    export = auth_client.get("/api/v1/settings/export-db")
    assert export.status_code == 200
    body = export.json()
    assert "companies" in body["tables"]
    # The preview must never embed a DSN or a credential.
    command = body["pg_dump_command"]
    assert "://" not in command
    assert "@" not in command


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_user_listing_requires_superuser(auth_client):
    response = auth_client.get("/api/v1/users")
    assert response.status_code == 403
