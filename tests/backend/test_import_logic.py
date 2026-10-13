"""Pure unit tests for import helpers (no database required)."""

from __future__ import annotations

from nexus.api.v1.import_ import (
    _clean_domain,
    _coerce_int,
    _company_quality,
    _contact_quality,
    _domain_from_url,
    _file_extension,
    _looks_like_company,
    _looks_like_contact,
    _normalize_row,
    _unique_columns,
    suggest_mapping,
)


def test_file_extension():
    assert _file_extension("data.csv") == ".csv"
    assert _file_extension("Report.XLSX") == ".xlsx"
    assert _file_extension("old.xls") == ".xls"
    assert _file_extension("macro.xlsm") == ".xlsx"
    assert _file_extension("noext") == ""


def test_normalize_row_trims_and_skips_blanks():
    raw = {" Email ": "  Ada@Example.com  ", "Phone": "   ", "X": "nan", "Y": "N/A"}
    mapping = {" Email ": "email", "Phone": "phone", "X": "notes", "Y": "source"}
    assert _normalize_row(raw, mapping) == {"email": "Ada@Example.com"}


def test_normalize_row_ignores_unmapped_destinations():
    assert _normalize_row({"a": "1"}, {"a": ""}) == {}


def test_classify_contact_vs_company():
    assert _looks_like_contact({"email": "a@b.com"})
    assert not _looks_like_contact({"company_name": "Acme"})
    assert _looks_like_company({"website": "https://acme.example"})
    assert _looks_like_company({"domain": "acme.example"})
    # Contact identity wins over a bare company_name.
    assert not _looks_like_company({"company_name": "Acme", "email": "a@b.com"})
    assert _looks_like_contact({"first_name": "Ada"})
    assert _looks_like_contact({"phone": "+1 555 0100"})


def test_contact_identity_wins_over_company_website():
    """A person's row is a contact even when it carries the employer's website.

    Regression test: the website/domain check used to short-circuit before the
    contact check, so a spreadsheet with a "Company Website" column next to
    name and email imported the company and silently dropped every person
    field in the row.
    """
    mixed = {
        "company_name": "Helio Robotics",
        "website": "https://helio-robotics.example",
        "domain": "helio-robotics.example",
        "full_name": "Priya Raman",
        "job_title": "CTO",
        "email": "priya.raman@helio-robotics.example",
    }
    assert _looks_like_contact(mixed)
    assert not _looks_like_company(mixed)

    # Company-only rows are still companies.
    assert _looks_like_company({"company_name": "Helio Robotics", "website": "https://helio.example"})


def test_quality_scores_bounded():
    full = {
        "full_name": "Ada",
        "email": "a@b.com",
        "phone": "123",
        "linkedin_url": "https://x",
        "company_name": "Acme",
        "job_title": "CTO",
    }
    assert _contact_quality(full) == 100
    assert _contact_quality({}) == 0
    assert 0 <= _company_quality({"company_name": "Acme"}) <= 100
    assert _company_quality({}) == 0


def test_suggest_mapping_recognises_common_headers():
    mapping = suggest_mapping(["Company Name", "Work Email", "Job Title", "Employee Count", "Random"])
    assert mapping["Company Name"] == "company_name"
    assert mapping["Work Email"] == "email"
    assert mapping["Job Title"] == "job_title"
    assert mapping["Employee Count"] == "employee_count"
    assert "Random" not in mapping


def test_suggest_mapping_prefers_the_first_claimant():
    # "Name" alone maps to company_name; "Full Name" claims full_name.
    mapping = suggest_mapping(["Name", "Full Name"])
    assert mapping["Name"] == "company_name"
    assert mapping["Full Name"] == "full_name"


def test_unique_columns_dedupes_repeated_headers():
    assert _unique_columns(["Name", "Name", "Name"]) == ["Name", "Name_1", "Name_2"]
    assert _unique_columns(["a", ""]) == ["a", "column"]


def test_domain_helpers():
    assert _domain_from_url("https://www.acme.io/about") == "acme.io"
    assert _domain_from_url("acme.io") == "acme.io"
    assert _domain_from_url("not a url") is None
    assert _clean_domain("https://WWW.Acme.io/path") == "acme.io"
    assert _clean_domain("") is None


def test_coerce_int_handles_excel_floats_and_separators():
    assert _coerce_int(1200.0) == 1200
    assert _coerce_int("1,200") == 1200
    assert _coerce_int("") is None
    assert _coerce_int("not a number") is None
