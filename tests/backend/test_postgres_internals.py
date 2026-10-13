"""PostgreSQL-specific invariants: schema, extensions, search indexes and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from nexus.database import SNAPSHOT_TABLES

from .conftest import run_sql, run_sql_multi, sql_scalar, unique

EXPECTED_TABLES = {
    "users",
    "sessions",
    "companies",
    "contacts",
    "contact_emails",
    "contact_phones",
    "employment_history",
    "lists",
    "list_contacts",
    "list_companies",
    "tags",
    "contact_tags",
    "company_tags",
    "saved_searches",
    "saved_views",
    "import_jobs",
    "import_rows",
    "import_errors",
    "duplicate_candidates",
    "verification_events",
    "activity_logs",
    "audit_logs",
    "custom_fields",
    "custom_field_values",
    "settings",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_every_expected_table_exists(_database):
    found = {row["tablename"] for row in run_sql("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert EXPECTED_TABLES <= found, f"missing: {sorted(EXPECTED_TABLES - found)}"


def test_pg_trgm_extension_is_installed(_database):
    assert sql_scalar("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'") == "pg_trgm"


def test_generated_search_vectors_exist(_database):
    for table in ("companies", "contacts"):
        value = sql_scalar(
            "SELECT attgenerated FROM pg_attribute WHERE attrelid = CAST(:t AS regclass) AND attname = 'search_vector'",
            {"t": table},
        )
        # 's' means STORED generated column. asyncpg returns the "char" type
        # as bytes, so normalise before comparing.
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        assert value == "s", f"{table}.search_vector is not a stored generated column"


def test_gin_and_trigram_indexes_are_present(_database):
    definitions = {
        row["indexname"]: row["indexdef"]
        for row in run_sql("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
    }

    for name in (
        "ix_companies_search_vector",
        "ix_companies_name_trgm",
        "ix_contacts_search_vector",
        "ix_contacts_full_name_trgm",
    ):
        assert name in definitions, f"{name} is missing"
        assert "USING gin" in definitions[name]

    # Trigram indexes must be on the lowercased expression that the query
    # builder uses, otherwise the index cannot serve the search.
    assert "lower" in definitions["ix_companies_name_trgm"]
    assert "gin_trgm_ops" in definitions["ix_companies_name_trgm"]


def test_foreign_keys_use_cascades_or_set_null(_database):
    """Deleting a parent must never orphan its children."""
    rules = {
        row["constraint_name"]: row["delete_rule"]
        for row in run_sql(
            """
            SELECT tc.constraint_name, rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            """
        )
    }
    assert rules, "expected foreign keys to exist"
    assert all(rule != "NO ACTION" for rule in rules.values())


# ---------------------------------------------------------------------------
# Search behaviour
# ---------------------------------------------------------------------------


def test_tsvector_matches_prefix_and_trigram_matches_typo(auth_client, _database):
    company = auth_client.post("/api/v1/companies", json={"name": "Orbital Dynamics"}).json()

    prefix = run_sql("SELECT id FROM companies WHERE search_vector @@ to_tsquery('english', 'orbit:*')")
    assert company["id"] in [row["id"] for row in prefix]

    multiword = run_sql(
        "SELECT id FROM companies WHERE search_vector @@ to_tsquery('english', 'orbital:* & dynamic:*')"
    )
    assert company["id"] in [row["id"] for row in multiword]

    # Trigram similarity catches a misspelling of the whole value.
    typo = run_sql("SELECT id FROM companies WHERE lower(name) % 'orbital dynamicz'")
    assert company["id"] in [row["id"] for row in typo]


def test_trigram_index_is_used_for_search(_database):
    """Both trigram predicates must be servable by the GIN trigram index.

    ``enable_seqscan`` is disabled for the EXPLAIN so the test asserts index
    *eligibility* rather than whether the planner prefers a different plan for
    a small table.
    """
    run_sql("INSERT INTO companies (name) SELECT 'Planner Probe ' || g FROM generate_series(1, 500) g")
    run_sql("ANALYZE companies")

    plan_substring = "\n".join(
        row["QUERY PLAN"]
        for row in run_sql_multi(
            [
                "SET enable_seqscan = off",
                "EXPLAIN (COSTS OFF) SELECT id FROM companies WHERE lower(name) LIKE '%planner%'",
            ]
        )
    )
    assert "ix_companies_name_trgm" in plan_substring, plan_substring

    plan_fuzzy = "\n".join(
        row["QUERY PLAN"]
        for row in run_sql_multi(
            [
                "SET enable_seqscan = off",
                "EXPLAIN (COSTS OFF) SELECT id FROM companies WHERE lower(name) % 'planner probe'",
            ]
        )
    )
    assert "ix_companies_name_trgm" in plan_fuzzy, plan_fuzzy

    # The tsvector branch uses its own GIN index.
    plan_fulltext = "\n".join(
        row["QUERY PLAN"]
        for row in run_sql_multi(
            [
                "SET enable_seqscan = off",
                (
                    "EXPLAIN (COSTS OFF) SELECT id FROM companies "
                    "WHERE search_vector @@ to_tsquery('english', 'planner:*')"
                ),
            ]
        )
    )
    assert "ix_companies_search_vector" in plan_fulltext, plan_fulltext


def test_search_vector_updates_on_write(auth_client, _database):
    company = auth_client.post("/api/v1/companies", json={"name": "Stellarium Optics"}).json()
    auth_client.patch(f"/api/v1/companies/{company['id']}", json={"industry": "Photonics"})

    found = run_sql("SELECT id FROM companies WHERE search_vector @@ to_tsquery('english', 'photonic:*')")
    assert company["id"] in [row["id"] for row in found]


def test_technologies_are_searchable(auth_client, _database):
    company = auth_client.post(
        "/api/v1/companies", json={"name": "Stack Test", "technologies": ["Kubernetes", "gRPC"]}
    ).json()
    found = run_sql("SELECT id FROM companies WHERE search_vector @@ to_tsquery('english', 'kubernetes:*')")
    assert company["id"] in [row["id"] for row in found]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


def test_quality_score_check_constraint(_database):
    """data_quality_score is constrained to 0-100 by the database itself."""
    with pytest.raises(IntegrityError):
        run_sql("INSERT INTO companies (name, data_quality_score) VALUES ('Bad', 150)")


def test_import_strategy_check_constraint(_database):
    with pytest.raises(IntegrityError):
        run_sql("INSERT INTO import_jobs (filename, strategy) VALUES ('f.csv', 'bogus')")


def test_import_update_mode_check_constraint(_database):
    with pytest.raises(IntegrityError):
        run_sql("INSERT INTO import_jobs (filename, update_mode) VALUES ('f.csv', 'bogus')")


def test_duplicate_candidate_score_check_constraint(_database):
    with pytest.raises(IntegrityError):
        run_sql(
            "INSERT INTO duplicate_candidates (entity_type, record_id, match_id, match_type, match_score) "
            "VALUES ('company', 1, 2, 'name', 5.0)"
        )


def test_unique_tag_name(auth_client, _database):
    name = unique("tag")
    assert auth_client.post("/api/v1/tags", json={"name": name}).status_code == 201
    duplicate = auth_client.post("/api/v1/tags", json={"name": name})
    assert duplicate.status_code == 409, duplicate.text


def test_unique_list_name(auth_client, _database):
    name = unique("list")
    assert auth_client.post("/api/v1/lists", json={"name": name}).status_code == 201
    assert auth_client.post("/api/v1/lists", json={"name": name}).status_code == 409


def test_unique_custom_field_per_entity(auth_client, _database):
    field = auth_client.post(
        "/api/v1/custom-fields",
        json={"entity_type": "company", "name": unique("Field"), "field_type": "text"},
    ).json()
    duplicate = auth_client.post(
        "/api/v1/custom-fields",
        json={"entity_type": "company", "name": field["name"], "field_type": "text"},
    )
    assert duplicate.status_code == 409


def test_unique_constraint_rejects_duplicate_email(auth_client, _database):
    """The users.email unique constraint is enforced by the database itself."""
    run_sql("INSERT INTO users (email, username, hashed_password) VALUES ('dup@x.test', 'dup1', 'h')")
    with pytest.raises(IntegrityError):
        run_sql("INSERT INTO users (email, username, hashed_password) VALUES ('dup@x.test', 'dup2', 'h')")
    # A rejected insert must not leave the API unable to serve later requests.
    assert auth_client.get("/api/v1/companies").status_code == 200


# ---------------------------------------------------------------------------
# Cascade behaviour
# ---------------------------------------------------------------------------


def test_deleting_a_contact_removes_child_rows(auth_client, _database):
    contact = auth_client.post("/api/v1/contacts", json={"full_name": unique("Cascade")}).json()
    run_sql(
        "INSERT INTO contact_emails (contact_id, email) VALUES (:id, 'cascade@example.com')",
        {"id": contact["id"]},
    )
    assert sql_scalar("SELECT count(*) FROM contact_emails WHERE contact_id = :id", {"id": contact["id"]}) == 1

    auth_client.delete(f"/api/v1/contacts/{contact['id']}")
    assert sql_scalar("SELECT count(*) FROM contact_emails WHERE contact_id = :id", {"id": contact["id"]}) == 0


def test_deleting_a_user_revokes_their_sessions(client, _database):
    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    user_id = sql_scalar("SELECT id FROM users WHERE username = :u", {"u": token})
    assert sql_scalar("SELECT count(*) FROM sessions WHERE user_id = :i", {"i": user_id}) == 1

    run_sql("DELETE FROM users WHERE id = :i", {"i": user_id})
    assert sql_scalar("SELECT count(*) FROM sessions WHERE user_id = :i", {"i": user_id}) == 0


def test_merging_companies_moves_contacts_to_the_survivor(auth_client, _database):
    first = auth_client.post("/api/v1/companies", json={"name": "Merge Target", "domain": "merge-one.example"}).json()
    second = auth_client.post("/api/v1/companies", json={"name": "Merge Target", "domain": "merge-two.example"}).json()
    contact = auth_client.post(
        "/api/v1/contacts",
        json={"full_name": unique("Merged"), "company_id": second["id"], "company_name": "Merge Target"},
    ).json()

    auth_client.post("/api/v1/duplicates/scan")
    candidates = auth_client.get("/api/v1/duplicates", params={"status": "open"}).json()["items"]
    candidate = next(
        item
        for item in candidates
        if item["entity_type"] == "company" and {item["record_id"], item["match_id"]} == {first["id"], second["id"]}
    )
    auth_client.post(f"/api/v1/duplicates/{candidate['id']}/merge", json={"keep_record_id": first["id"]})

    company_id = sql_scalar("SELECT company_id FROM contacts WHERE id = :i", {"i": contact["id"]})
    assert company_id == first["id"]


# ---------------------------------------------------------------------------
# Backup surface
# ---------------------------------------------------------------------------


def test_snapshot_table_list_covers_the_schema():
    assert "companies" in SNAPSHOT_TABLES
    assert "sessions" in SNAPSHOT_TABLES
    assert "import_errors" in SNAPSHOT_TABLES
    # Children must be restored after their parents, so order matters.
    assert SNAPSHOT_TABLES.index("users") < SNAPSHOT_TABLES.index("companies")
    assert SNAPSHOT_TABLES.index("companies") < SNAPSHOT_TABLES.index("contacts")
    assert SNAPSHOT_TABLES.index("import_jobs") < SNAPSHOT_TABLES.index("import_rows")


def test_backup_snapshot_excludes_session_tokens(auth_client):
    """A snapshot must never contain material that can authenticate a user."""
    import json

    export = auth_client.get("/api/v1/settings/download-db")
    assert export.status_code == 200
    payload = json.loads(export.text)

    assert "sessions" not in payload["tables"]
    assert "users" in payload["tables"]
    assert payload["engine"] == "postgresql"
    assert payload["schema_version"] == "0001_initial"
