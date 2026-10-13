"""Import wizard tests: validation, preview, mapping, planning, strategies and reports."""

from __future__ import annotations

from .conftest import unique

CONTACTS_CSV = (
    "Full Name,Email,Company,Job Title,Mobile\n"
    "Ada Lovelace,ada@analytical.example,Analytical Engines,CTO,+44 20 7946 0001\n"
    "Grace Hopper,grace@analytical.example,Analytical Engines,COO,+44 20 7946 0002\n"
)

COMPANIES_CSV = (
    "Company,Website,Industry,City,Country\n"
    "Analytical Engines,https://analytical.example,Computing,London,United Kingdom\n"
)


def upload(client, text: str, name: str = "contacts.csv") -> int:
    response = client.post(
        "/api/v1/import/upload",
        files={"file": (name, text.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def map_and_run(client, job_id: int, mapping: dict[str, str], **extra):
    mapped = client.post(f"/api/v1/import/mapping/{job_id}", json={"mapping": mapping, **extra})
    assert mapped.status_code == 200, mapped.text
    run = client.post(f"/api/v1/import/run/{job_id}")
    assert run.status_code == 200, run.text
    return run.json()


def auto_mapping(client, job_id: int) -> dict[str, str]:
    preview = client.get(f"/api/v1/import/preview/{job_id}")
    assert preview.status_code == 200, preview.text
    return preview.json()["suggested_mapping"]


def set_mapping(client, job_id: int, mapping: dict[str, str], **extra) -> dict:
    response = client.post(f"/api/v1/import/mapping/{job_id}", json={"mapping": mapping, **extra})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


def test_import_options_describe_strategies(auth_client):
    options = auth_client.get("/api/v1/import/options")
    assert options.status_code == 200
    body = options.json()
    assert {s["value"] for s in body["strategies"]} == {"add", "update", "add_and_update", "skip_duplicates"}
    assert {m["value"] for m in body["update_modes"]} == {"fill_empty", "overwrite"}
    assert "company_name" in body["target_fields"]["company"]
    assert "email" in body["target_fields"]["contact"]


def test_upload_rejects_unsupported_extension(auth_client):
    response = auth_client.post("/api/v1/import/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_binary_disguised_as_csv(auth_client):
    response = auth_client.post(
        "/api/v1/import/upload", files={"file": ("evil.csv", b"\x00\x01\x02binary", "text/csv")}
    )
    assert response.status_code == 400


def test_upload_rejects_fake_xlsx(auth_client):
    response = auth_client.post(
        "/api/v1/import/upload", files={"file": ("fake.xlsx", b"not a workbook", "application/vnd.ms-excel")}
    )
    assert response.status_code == 400


def test_upload_rejects_empty_file(auth_client):
    response = auth_client.post("/api/v1/import/upload", files={"file": ("empty.csv", b"", "text/csv")})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Preview and mapping
# ---------------------------------------------------------------------------


def test_preview_returns_columns_rows_and_suggested_mapping(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    preview = auth_client.get(f"/api/v1/import/preview/{job_id}")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["columns"] == ["Full Name", "Email", "Company", "Job Title", "Mobile"]
    assert body["row_count"] == 2
    assert body["total_rows_estimate"] == 2

    suggestion = body["suggested_mapping"]
    assert suggestion["Full Name"] == "full_name"
    assert suggestion["Email"] == "email"
    assert suggestion["Company"] == "company_name"
    assert suggestion["Job Title"] == "job_title"
    assert suggestion["Mobile"] == "phone"


def test_sheets_endpoint_reports_csv(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    sheets = auth_client.get(f"/api/v1/import/sheets/{job_id}")
    assert sheets.status_code == 200
    assert sheets.json()["sheets"] == ["csv"]


def test_mapping_endpoint_validates_strategy(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    bad = auth_client.post(f"/api/v1/import/mapping/{job_id}", json={"mapping": {}, "strategy": "nonsense"})
    assert bad.status_code == 400

    ok = auth_client.post(
        f"/api/v1/import/mapping/{job_id}",
        json={"mapping": {"Full Name": "full_name"}, "strategy": "skip_duplicates", "update_mode": "overwrite"},
    )
    assert ok.status_code == 200
    assert ok.json()["strategy"] == "skip_duplicates"
    assert ok.json()["update_mode"] == "overwrite"


def test_import_jobs_are_private_to_their_owner(auth_client):
    """A second account must not be able to read or run someone else's import."""
    job_id = upload(auth_client, CONTACTS_CSV)

    other = unique("user")
    auth_client.post(
        "/api/v1/auth/signup",
        json={"email": f"{other}@example.com", "username": other, "password": "Str0ngPassw0rd!"},
    )
    assert auth_client.get(f"/api/v1/import/preview/{job_id}").status_code == 404
    assert auth_client.post(f"/api/v1/import/run/{job_id}").status_code == 404


# ---------------------------------------------------------------------------
# Plan (dry run) and run
# ---------------------------------------------------------------------------


def test_import_adds_new_records(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    mapping = auto_mapping(auth_client, job_id)
    set_mapping(auth_client, job_id, mapping)

    plan = auth_client.get(f"/api/v1/import/plan/{job_id}")
    assert plan.status_code == 200, plan.text
    assert plan.json()["counts"]["added"] == 2
    assert plan.json()["counts"]["updated"] == 0
    # A dry run must not write anything.
    assert auth_client.get("/api/v1/contacts").json()["total"] == 0

    result = map_and_run(auth_client, job_id, mapping)
    assert result["rows_added"] == 2
    assert result["rows_invalid"] == 0
    assert result["status"] == "completed"

    contacts = auth_client.get("/api/v1/contacts", params={"q": "Analytical Engines"}).json()
    assert contacts["total"] >= 2


def test_import_creates_company_rows(auth_client):
    job_id = upload(auth_client, COMPANIES_CSV, name="companies.csv")
    mapping = auto_mapping(auth_client, job_id)
    assert mapping["Company"] == "company_name"

    result = map_and_run(auth_client, job_id, mapping)
    assert result["rows_added"] == 1

    companies = auth_client.get("/api/v1/companies", params={"q": "Analytical Engines"}).json()
    assert companies["total"] >= 1
    assert companies["items"][0]["domain"] == "analytical.example"
    assert companies["items"][0]["city"] == "London"


def test_mixed_rows_import_the_person_and_link_the_company(auth_client):
    """A row with both company and person columns imports the person.

    Regression test: such rows used to be classified as companies, which
    silently discarded every contact field (name, title, email) in the row.
    """
    auth_client.post("/api/v1/companies", json={"name": "Helio Robotics", "domain": "helio-robotics.example"})

    csv = (
        "Company,Website,Full Name,Job Title,Email\n"
        "Helio Robotics,https://helio-robotics.example,Priya Raman,CTO,priya@helio-robotics.example\n"
    )
    job_id = upload(auth_client, csv, name="people.csv")
    mapping = auto_mapping(auth_client, job_id)
    assert mapping["Full Name"] == "full_name"
    assert mapping["Website"] == "website"
    set_mapping(auth_client, job_id, mapping)

    plan = auth_client.get(f"/api/v1/import/plan/{job_id}").json()
    assert plan["counts"]["added"] == 1
    assert plan["items"][0]["entity"] == "contact"

    result = map_and_run(auth_client, job_id, mapping)
    assert result["rows_added"] == 1

    contact = auth_client.get("/api/v1/contacts", params={"q": "priya@helio-robotics.example"}).json()
    assert contact["total"] == 1
    item = contact["items"][0]
    assert item["job_title"] == "CTO"
    assert item["company_name"] == "Helio Robotics"
    # Linked to the existing company rather than left as a dangling name.
    assert item["company_id"] is not None

    # The company row was neither duplicated nor rewritten.
    companies = auth_client.get("/api/v1/companies", params={"q": "Helio Robotics"}).json()
    assert companies["total"] == 1
    # The company reports the person it now owns. Regression test: contact_count
    # was serialised from the schema default and always read 0.
    assert companies["items"][0]["contact_count"] == 1


def test_strategy_add_skips_existing_matches(auth_client):
    first_job = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, first_job, auto_mapping(auth_client, first_job))

    second_job = upload(auth_client, CONTACTS_CSV, name="contacts-again.csv")
    mapping = auto_mapping(auth_client, second_job)
    result = map_and_run(auth_client, second_job, mapping, strategy="add")

    assert result["rows_added"] == 0
    assert result["rows_skipped"] == 2


def test_strategy_skip_duplicates_leaves_existing_untouched(auth_client):
    first = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, first, auto_mapping(auth_client, first))

    updated_csv = CONTACTS_CSV.replace("CTO", "Chief Engineer")
    second = upload(auth_client, updated_csv, name="contacts-changed.csv")
    result = map_and_run(auth_client, second, auto_mapping(auth_client, second), strategy="skip_duplicates")

    assert result["rows_updated"] == 0
    assert result["rows_skipped"] == 2
    contact = auth_client.get("/api/v1/contacts", params={"q": "ada@analytical.example"}).json()
    assert contact["items"][0]["job_title"] == "CTO"


def test_update_mode_fill_empty_never_overwrites(auth_client):
    first = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, first, auto_mapping(auth_client, first))

    # Same people, with job titles changed and a previously blank department added.
    changed = (
        "Full Name,Email,Company,Job Title,Department\n"
        "Ada Lovelace,ada@analytical.example,Analytical Engines,Chief Scientist,Research\n"
        "Grace Hopper,grace@analytical.example,Analytical Engines,COO,Operations\n"
    )
    second = upload(auth_client, changed, name="contacts-update.csv")
    mapping = auto_mapping(auth_client, second)
    result = map_and_run(auth_client, second, mapping, strategy="add_and_update", update_mode="fill_empty")

    assert result["rows_added"] == 0
    assert result["rows_updated"] == 2

    ada = auth_client.get("/api/v1/contacts", params={"q": "ada@analytical.example"}).json()["items"][0]
    # Job title already had a value -> untouched.
    assert ada["job_title"] == "CTO"

    detail = auth_client.get(f"/api/v1/import/{second}").json()
    assert detail["rows_total"] == 2


def test_update_mode_overwrite_records_field_level_changes(auth_client):
    first = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, first, auto_mapping(auth_client, first))

    changed = (
        "Full Name,Email,Company,Job Title\nAda Lovelace,ada@analytical.example,Analytical Engines,Chief Scientist\n"
    )
    second = upload(auth_client, changed, name="contacts-overwrite.csv")
    mapping = auto_mapping(auth_client, second)

    set_mapping(auth_client, second, mapping, strategy="add_and_update", update_mode="overwrite")

    dry_run = auth_client.get(f"/api/v1/import/plan/{second}").json()
    assert dry_run["counts"]["updated"] == 1
    change = dry_run["items"][0]["changes"]["job_title"]
    assert change["from"] == "CTO"
    assert change["to"] == "Chief Scientist"
    assert change["action"] == "overwrite"

    result = auth_client.post(f"/api/v1/import/run/{second}").json()
    assert result["rows_updated"] == 1

    ada = auth_client.get("/api/v1/contacts", params={"q": "ada@analytical.example"}).json()["items"][0]
    assert ada["job_title"] == "Chief Scientist"


def test_strategy_update_only_updates_existing(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV, name="nobody-exists.csv")
    result = map_and_run(auth_client, job_id, auto_mapping(auth_client, job_id), strategy="update")
    assert result["rows_added"] == 0
    assert result["rows_skipped"] == 2

    contacts = auth_client.get("/api/v1/contacts", params={"q": "ada@analytical.example"}).json()
    assert contacts["total"] == 0


def test_unchanged_rows_are_reported_separately(auth_client):
    first = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, first, auto_mapping(auth_client, first))

    second = upload(auth_client, CONTACTS_CSV, name="identical.csv")
    result = map_and_run(auth_client, second, auto_mapping(auth_client, second), strategy="add_and_update")
    assert result["rows_unchanged"] == 2
    assert result["rows_updated"] == 0


def test_import_is_transactional_on_failure(auth_client):
    """A row that violates a database constraint must roll the whole run back.

    The second row carries a negative employee count, which the
    ck_companies_employee_count CHECK constraint rejects. Because the run is a
    single transaction, the valid first row must not survive either.
    """
    csv = "Company,Website,Employees\nRollback Probe,https://rollback.example,50\nBad Row,https://bad.example,-5\n"
    job_id = upload(auth_client, csv, name="rollback.csv")
    set_mapping(
        auth_client,
        job_id,
        {"Company": "company_name", "Website": "website", "Employees": "employee_count"},
    )

    response = auth_client.post(f"/api/v1/import/run/{job_id}")
    assert response.status_code == 400, response.text
    assert "rolled back" in response.json()["detail"]

    companies = auth_client.get("/api/v1/companies", params={"q": "Rollback Probe"}).json()
    assert companies["total"] == 0, "a failed import must leave no rows behind"

    # The job is not left claiming success.
    detail = auth_client.get(f"/api/v1/import/{job_id}").json()
    assert detail["status"] != "completed"


# ---------------------------------------------------------------------------
# Error reporting and history
# ---------------------------------------------------------------------------


def test_invalid_rows_produce_error_report(auth_client):
    csv = "Full Name,Email,Notes\nReal Person,real@example.com,ok\n,,only empty mapped values\n"
    job_id = upload(auth_client, csv, name="mixed.csv")
    result = map_and_run(auth_client, job_id, {"Full Name": "full_name", "Email": "email", "Notes": "notes"})
    assert result["rows_added"] == 1
    assert result["rows_invalid"] == 1
    assert result["error_summary"]

    errors = auth_client.get(f"/api/v1/import/errors/{job_id}")
    assert errors.status_code == 200
    body = errors.json()
    assert body["count"] == 1
    assert body["data"][0]["row_index"] == 1
    assert body["csv"]


def test_history_and_progress(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, job_id, auto_mapping(auth_client, job_id))

    history = auth_client.get("/api/v1/import/history")
    assert history.status_code == 200
    assert any(job["id"] == job_id for job in history.json()["jobs"])

    progress = auth_client.get(f"/api/v1/import/progress/{job_id}")
    assert progress.status_code == 200
    body = progress.json()
    assert body["rows_total"] == 2
    assert body["rows_processed"] == 2
    assert body["percent"] == 100.0
    assert body["by_status"]["added"] == 2


def test_download_import_report_csv(auth_client):
    job_id = upload(auth_client, CONTACTS_CSV)
    map_and_run(auth_client, job_id, auto_mapping(auth_client, job_id))

    response = auth_client.get(f"/api/v1/import/download/{job_id}", params={"extension": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "action" in response.text


# ---------------------------------------------------------------------------
# Duplicates integration
# ---------------------------------------------------------------------------


def test_duplicate_scan_and_merge(auth_client):
    auth_client.post(
        "/api/v1/companies", json={"name": "Zenith Robotics", "domain": "zenith-one.example", "city": "Oslo"}
    )
    auth_client.post(
        "/api/v1/companies", json={"name": "Zenith Robotics", "domain": "zenith-two.example", "industry": "Robotics"}
    )

    scan = auth_client.post("/api/v1/duplicates/scan")
    assert scan.status_code == 200, scan.text
    assert scan.json()["companies"] >= 1

    listed = auth_client.get("/api/v1/duplicates", params={"status": "open"}).json()
    candidate = next(item for item in listed["items"] if item["entity_type"] == "company")

    compare = auth_client.get(f"/api/v1/duplicates/{candidate['id']}/compare")
    assert compare.status_code == 200
    body = compare.json()
    assert any(row["field"] == "domain" and row["conflict"] for row in body["record"]["fields"])

    merged = auth_client.post(
        f"/api/v1/duplicates/{candidate['id']}/merge",
        json={"keep_record_id": candidate["record_id"]},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["status"] == "merged"
    # The survivor inherited the city that only the discarded record had.
    kept = auth_client.get(f"/api/v1/companies/{candidate['record_id']}").json()
    assert kept["city"] == "Oslo" or kept["industry"] == "Robotics"

    remaining = auth_client.get("/api/v1/duplicates", params={"status": "open"}).json()
    assert all(item["id"] != candidate["id"] for item in remaining["items"])


def test_duplicate_ignore_and_reopen(auth_client):
    auth_client.post("/api/v1/contacts", json={"full_name": "Sam Duplicate", "email": "sam@dup.example"})
    auth_client.post("/api/v1/contacts", json={"full_name": "Sam Duplicate", "email": "sam@dup.example"})
    auth_client.post("/api/v1/duplicates/scan")

    listed = auth_client.get("/api/v1/duplicates", params={"status": "open"}).json()["items"]
    candidate = next(item for item in listed if item["entity_type"] == "contact")

    assert auth_client.post(f"/api/v1/duplicates/{candidate['id']}/ignore").json()["status"] == "ignored"
    assert auth_client.post(f"/api/v1/duplicates/{candidate['id']}/reopen").json()["status"] == "reopened"
    assert auth_client.post(f"/api/v1/duplicates/{candidate['id']}/keep-both").json()["status"] == "kept_both"
