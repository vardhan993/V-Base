"""Explicit ETL: the CSV exports in ``uploads/`` into the unified schema.

This is deliberately **not** a blind loop over ``*.csv``. Three different
spreadsheets are shipped with the project and each carries its own header, so
each one is declared below by its exact column tuple and gets its own
transform that names every source column it reads:

``wide``       14 columns mixing a company and a person on one row
               (``Company Name … Technologies`` + ``Full Name … Seniority``).
               It yields *two* records and is split here rather than being
               treated as one flat table.

``companies``  company attributes only. Its last column is ``Company
               LinkedIn`` - the company *page*, which maps to
               ``companies.linkedin_url``. In the wide file the identically
               named ``LinkedIn`` column holds a person's profile and maps to
               ``contacts.linkedin_url``. The two are never interchangeable.

``contacts``   person attributes only, keyed by a bare ``Company`` name with no
               company attributes to fill in, so the company is resolved by
               name (or created as a stub) purely as a link target.

A file whose header does not match a declaration is reported and skipped
instead of being guessed at, and byte-identical re-exports are skipped too -
the project's own test fixtures are malformed on purpose, and this is what
keeps them out of the production tables.

Load semantics: idempotent upserts keyed on ``domain``/lower-cased ``name``
for companies and lower-cased ``email`` (falling back to name + company) for
contacts. Existing non-empty fields are left alone unless ``--overwrite`` is
given, so running the command twice changes nothing the second time.

Nothing here is ever marked "verified": V-Base only labels an email or phone
verified when a real ``verification_events`` row recorded it, and this script
does not create one.

Usage::

    python -m nexus.commands.etl list
    python -m nexus.commands.etl run --dry-run
    python -m nexus.commands.etl run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, select

from nexus.api.v1.import_ import (
    _as_list,
    _clean_domain,
    _coerce_int,
    _company_quality,
    _contact_quality,
)
from nexus.core.config import settings
from nexus.core.db import session_scope
from nexus.database import Company, Contact

logger = logging.getLogger("vbase.etl")

Kind = Literal["wide", "companies", "contacts", "research", "research_slim", "leads"]
Phase = Literal["companies", "contacts"]

# ---------------------------------------------------------------------------
# Column declarations - the contract for every file we accept
# ---------------------------------------------------------------------------

#: Denormalised export: company attributes and person attributes on one row.
WIDE_COLUMNS: tuple[str, ...] = (
    "Company Name",
    "Website",
    "Industry",
    "Employees",
    "City",
    "Country",
    "Technologies",
    "Full Name",
    "Job Title",
    "Department",
    "Email",
    "Phone",
    "LinkedIn",
    "Seniority",
)

#: Company-only export. Note ``Company LinkedIn`` (the company page).
COMPANY_COLUMNS: tuple[str, ...] = (
    "Company",
    "Website",
    "Industry",
    "Employees",
    "City",
    "Country",
    "Technologies",
    "Company LinkedIn",
)

#: Person-only export. Note ``LinkedIn`` (the person's profile).
CONTACT_COLUMNS: tuple[str, ...] = (
    "Company",
    "Full Name",
    "Job Title",
    "Department",
    "Seniority",
    "Email",
    "Phone",
    "LinkedIn",
)

#: Enrichment-export research file: 173 columns, company and person on one
#: row, plus a long tail of validation scores and address parts that have no
#: home in the schema.
#:
#: The full header is declared rather than only the columns we read, so a
#: re-export that shifts a column is detected instead of silently mis-mapped.
#: Note that ``First Name`` and ``Last Name`` each appear **twice** (the second
#: copy holds the values). ``csv.DictReader`` collapses duplicate headers and
#: keeps only the last one, so this transform deliberately reads the unique
#: ``Contact Full Name`` and splits it instead of relying on those columns.
RESEARCH_COLUMNS: tuple[str, ...] = (
    "Research Date",
    "Contact Full Name",
    "First Name",
    "Middle Name",
    "First Name",
    "Last Name",
    "Last Name",
    "Title",
    "Department",
    "Seniority",
    "Company Name",
    "Company Name - Cleaned",
    "Website",
    "Lists",
    "Primary Email",
    "List",
    "Intel",
    "Contact LI Profile URL",
    "Email 1",
    "Email 1 Validation",
    "Email 1 Total AI",
    "Email 2",
    "Email 2 Validation",
    "Email 2 Total AI",
    "Email 3",
    "Email 3 Validation",
    "Email 3 Total AI",
    "Email 4",
    "Email 4 Validation",
    "Email 4 Total AI",
    "Email 5",
    "Email 5 Validation",
    "Email 5 Total AI",
    "Email 6",
    "Email 6 Validation",
    "Email 6 Total AI",
    "Email 7",
    "Email 7 Validation",
    "Email 7 Total AI",
    "Email 8",
    "Email 8 Validation",
    "Email 8 Total AI",
    "Email 9",
    "Email 9 Validation",
    "Email 9 Total AI",
    "Email 10",
    "Email 10 Validation",
    "Email 10 Total AI",
    "Personal Email",
    "Personal Email Validation",
    "Personal Email Total AI",
    "Personal Email 2",
    "Personal Email 2 Validation",
    "Personal Email 2 Total AI",
    "Personal Email 3",
    "Personal Email 3 Validation",
    "Personal Email 3 Total AI",
    "Contact Phone 1",
    "Contact Phone 1 Total AI",
    "Company Phone 1",
    "Company Phone 1 Total AI",
    "Contact Phone 2",
    "Contact Phone 2 Total AI",
    "Company Phone 2",
    "Company Phone 2 Total AI",
    "Contact Phone 3",
    "Contact Phone 3 Total AI",
    "Company Phone 3",
    "Company Phone 3 Total AI",
    "Contact Phone 4",
    "Contact Phone 4 Total AI",
    "Company Phone 4",
    "Company Phone 4 Total AI",
    "Contact Phone 5",
    "Contact Phone 5 Total AI",
    "Company Phone 5",
    "Company Phone 5 Total AI",
    "Contact Phone 6",
    "Contact Phone 6 Total AI",
    "Company Phone 6",
    "Company Phone 6 Total AI",
    "Contact Phone 7",
    "Contact Phone 7 Total AI",
    "Company Phone 7",
    "Company Phone 7 Total AI",
    "Contact Phone 8",
    "Contact Phone 8 Total AI",
    "Company Phone 8",
    "Company Phone 8 Total AI",
    "Contact Phone 9",
    "Contact Phone 9 Total AI",
    "Company Phone 9",
    "Company Phone 9 Total AI",
    "Contact Phone 10",
    "Contact Phone 10 Total AI",
    "Current CRM User Email",
    "Company Phone 10",
    "Company Phone 10 Total AI",
    "Contact Mobile Phone",
    "Contact Mobile Phone 1 Total AI",
    "Contact Mobile Phone 2",
    "Contact Mobile Phone 2 Total AI",
    "Contact Mobile Phone 3",
    "Contact City",
    "Contact Mobile Phone 3 Total AI",
    "Contact Mobile Phone 4",
    "Contact State",
    "Contact State Abbr",
    "Contact Mobile Phone 4 Total AI",
    "Contact Mobile Phone 5",
    "Contact Post Code",
    "Contact County",
    "Contact Mobile Phone 5 Total AI",
    "Contact Country",
    "Contact Mobile Phone 6",
    "Contact Country (Alpha 2)",
    "Contact Mobile Phone 6 Total AI",
    "Contact Country (Alpha 3)",
    "Contact Mobile Phone 7",
    "Contact Country - Numeric",
    "Contact Mobile Phone 7 Total AI",
    "Contact Mobile Phone 8",
    "Contact Mobile Phone 8 Total AI",
    "Contact Mobile Phone 9",
    "Contact Mobile Phone 9 Total AI",
    "Contact Mobile Phone 10",
    "Contact Mobile Phone 10 Total AI",
    "Contact Location",
    "Company County",
    "Contact Location - City",
    "Contact Location - State",
    "Contact Location - State Abbreviation",
    "Contact Location - ZIP",
    "Contact Location - Country",
    "Contact Location - Country Alpha-2 Code",
    "Contact Location - Country Alpha-3 Code",
    "Contact Location - Country Numeric Code",
    "Company Location",
    "Company Street 1",
    "Company Street 2",
    "Company Street 3",
    "Company City",
    "Company State",
    "Company State Abbr",
    "Company Post Code",
    "Company Country",
    "Company Country (Alpha 2)",
    "Company Country (Alpha 3)",
    "Company Country - Numeric",
    "Company Annual Revenue",
    "Company Description",
    "Company Website Domain",
    "Company Founded Date",
    "Company Industry",
    "Company LI Profile Url",
    "Company LinkedIn ID",
    "Company Revenue Range",
    "Company Staff Count",
    "Company Staff Count Range",
    "Seamless Username",
    "CRM Account ID",
    "CRM & Social",
    "Date Imported",
    "leadSource",
    "Contact Phone",
    "Location",
    "Current CRM User ID",
    "SIC Code",
    "NAICS Code",
    "Job Alert",
    "Former Position",
    "Time in Current Position",
    "Time in Current Company",
)

#: Narrower re-export of the same research dataset: same 22,903 rows, 65 of
#: the 173 columns, and a different column **order** (``Title`` sits between
#: the two ``Last Name`` columns). It drops ``Department``, ``Seniority``,
#: ``Contact City``, ``Company State`` and ``Company Staff Count``, so those
#: fields simply come from wherever they are present - ``_merge`` only ever
#: fills blanks, never erases.
RESEARCH_SLIM_COLUMNS: tuple[str, ...] = (
    "Research Date",
    "Contact Full Name",
    "First Name",
    "First Name",
    "Last Name",
    "Title",
    "Last Name",
    "Company Name",
    "Company Name - Cleaned",
    "Website",
    "Primary Email",
    "Contact LI Profile URL",
    "Email 1",
    "Email 1 Validation",
    "Email 1 Total AI",
    "Email 2",
    "Email 2 Validation",
    "Email 2 Total AI",
    "Email 3",
    "Email 3 Validation",
    "Email 3 Total AI",
    "Personal Email",
    "Personal Email 2",
    "Personal Email 2 Validation",
    "Personal Email 2 Total AI",
    "Personal Email 3",
    "Personal Email 3 Validation",
    "Personal Email 3 Total AI",
    "Contact Phone 1",
    "Contact Phone 1 Total AI",
    "Company Phone 1",
    "Company Phone 1 Total AI",
    "Current CRM User Email",
    "Contact Mobile Phone",
    "Contact Mobile Phone 1 Total AI",
    "Contact Mobile Phone 2",
    "Contact Mobile Phone 2 Total AI",
    "Contact Mobile Phone 3",
    "Contact Mobile Phone 3 Total AI",
    "Contact State",
    "Contact Mobile Phone 4",
    "Contact Mobile Phone 4 Total AI",
    "Contact Mobile Phone 5",
    "Contact Mobile Phone 5 Total AI",
    "Contact Country",
    "Company Location",
    "Company City",
    "Company Country",
    "Company Annual Revenue",
    "Company Description",
    "Company Website Domain",
    "Company Founded Date",
    "Company Industry",
    "Company LI Profile Url",
    "Company LinkedIn ID",
    "Job Postings",
    "Paid Search Intelligence",
    "SEO Research",
    "Social Media Posts",
    "Web Technologies",
    "Wikipedia",
    "Seamless Username",
    "Date Imported",
    "leadSource",
    "Contact Phone",
)

#: Hiring-signal export: 13 columns, no email or phone at all, and a person
#: split across separate ``First Name`` / ``Last Name`` columns.
LEADS_COLUMNS: tuple[str, ...] = (
    "First Name",
    "Last Name",
    "Lead Title",
    "Location",
    "Lead LinkedIn",
    "Company Name",
    "Company Location",
    "Company Domain",
    "Company LinkedIn URL",
    "Latest Funding",
    "Open Job Title",
    "Open Job Url",
    "Jobcount",
)

#: Header tuple -> kind. Exact match only; there is no fuzzy fallback.
COLUMNS_BY_KIND: dict[tuple[str, ...], Kind] = {
    WIDE_COLUMNS: "wide",
    COMPANY_COLUMNS: "companies",
    CONTACT_COLUMNS: "contacts",
    RESEARCH_COLUMNS: "research",
    RESEARCH_SLIM_COLUMNS: "research_slim",
    LEADS_COLUMNS: "leads",
}

#: Which phase(s) each kind contributes records to. ``wide`` and ``research``
#: contribute to both, which is why the run is a pass over phases rather than
#: over files.
PHASES_BY_KIND: dict[Kind, tuple[Phase, ...]] = {
    "companies": ("companies",),
    "contacts": ("contacts",),
    "wide": ("companies", "contacts"),
    "research": ("companies", "contacts"),
    "research_slim": ("companies", "contacts"),
    "leads": ("companies", "contacts"),
}

#: Matches the company-size buckets the Companies filter and the
#: companies-by-size chart group on.
_SIZE_BANDS: tuple[tuple[int, str], ...] = (
    (10, "1-10"),
    (50, "11-50"),
    (200, "51-200"),
    (500, "201-500"),
    (1000, "501-1000"),
)


@dataclass(frozen=True)
class FileSpec:
    """A recognised file: its own path, its own exact columns, its own kind."""

    path: Path
    columns: tuple[str, ...]
    kind: Kind
    phases: tuple[Phase, ...]
    digest: str


@dataclass
class FileReport:
    path: Path
    kind: Kind
    rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    companies_created_for_contacts: int = 0
    #: Values shortened to fit their column; reported, never silent.
    truncated: int = 0


@dataclass
class Discovery:
    specs: list[FileSpec] = field(default_factory=list)
    unrecognised: list[Path] = field(default_factory=list)
    duplicates: list[tuple[Path, Path]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small normalisers
# ---------------------------------------------------------------------------


def _text(row: dict[str, Any], key: str) -> str | None:
    """Read one named column as a stripped string, or ``None`` when blank."""
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _email(value: Any) -> str | None:
    """Lower-case and validate an address; reject anything without an ``@``."""
    text = _text({"email": value}, "email")
    if not text or "@" not in text or text.startswith("@") or text.endswith("@"):
        return None
    return text.lower()


def _phone(value: Any) -> str | None:
    text = _text({"phone": value}, "phone")
    if not text:
        return None
    if len(text.replace(" ", "").replace("-", "").replace("+", "")) < 6:
        return None
    return text


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Split ``Ada Lindqvist`` -> ``("Ada", "Lindqvist")``; one token -> last is empty."""
    if not full_name:
        return None, None
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _size_band(employees: int | None) -> str | None:
    """Derive the UI's size bucket from a headcount."""
    if employees is None:
        return None
    if employees <= 0:
        return None
    for ceiling, label in _SIZE_BANDS:
        if employees <= ceiling:
            return label
    return "1000+"


def _year(value: Any) -> int | None:
    """Read a founded date as a year: ``2017`` or ``2017-05-04`` -> ``2017``."""
    text = _text({"v": value}, "v")
    if not text:
        return None
    digits = text[:4]
    if len(digits) == 4 and digits.isdigit():
        year = int(digits)
        if 1600 <= year <= 2200:  # matches the CHECK constraint on companies
            return year
    return None


def _headcount(value: Any) -> int | None:
    """Parse a headcount, dropping anything the schema would reject.

    ``companies.employee_count`` carries ``CHECK (employee_count >= 0)``, and
    the research export really does contain negative staff counts (a ``-9``
    from whatever upstream calculation produced it). ``_coerce_int`` itself is
    shared with the Import Center and is not changed, so the constraint is
    honoured here instead.
    """
    parsed = _coerce_int(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _absolute_url(value: Any) -> str | None:
    """Give a scheme-less host a scheme so the UI's link renders as a link.

    The research export stores ``signalwire.com`` while the schema's
    ``website`` column is a URL everywhere else (``https://…``). Prefixing is a
    normalisation, not an invention: the host is taken verbatim from the file
    and only the scheme is added.
    """
    text = _text({"v": value}, "v")
    if not text:
        return None
    if "://" in text:
        return text
    return f"https://{text.removeprefix('www.')}"


def _city_from(value: Any) -> str | None:
    """``Fairfax, Virginia, United States`` -> ``Fairfax``.

    The leads export writes one ``Location`` field as ``City, State, Country``
    (or, inconsistently, ``New York City Metropolitan Area`` with no commas).
    Only the leading segment can be called a city with confidence; the rest is
    state and country, and ``contacts`` has no state column to hold them.
    """
    text = _text({"v": value}, "v")
    if not text:
        return None
    return text.split(",")[0].strip() or None


# ---------------------------------------------------------------------------
# Transforms - one per file kind, each naming every column it reads
# ---------------------------------------------------------------------------


def _company_from_wide(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Company Name … Technologies`` -> a ``companies`` payload."""
    website = _text(row, "Website")
    employees = _headcount(row.get("Employees"))
    return {
        "name": _text(row, "Company Name"),
        "website": website,
        "domain": _clean_domain(website),
        "industry": _text(row, "Industry"),
        "employee_count": employees,
        "company_size": _size_band(employees),
        "city": _text(row, "City"),
        "country": _text(row, "Country"),
        "technologies": _as_list(row.get("Technologies")),
        "source": source,
    }


def _contact_from_wide(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Full Name … Seniority`` -> a ``contacts`` payload, linked by company name."""
    full_name = _text(row, "Full Name")
    first_name, last_name = _split_name(full_name)
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": _text(row, "Job Title"),
        "department": _text(row, "Department"),
        "seniority": _text(row, "Seniority"),
        "email": _email(row.get("Email")),
        "phone": _phone(row.get("Phone")),
        "linkedin_url": _text(row, "LinkedIn"),
        "company_name": _text(row, "Company Name"),
        "city": _text(row, "City"),
        "country": _text(row, "Country"),
        "source": source,
    }


def _company_from_companies(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Company … Company LinkedIn`` -> a ``companies`` payload.

    ``Company LinkedIn`` is a ``/company/`` page URL, so it belongs on the
    company - unlike the wide file's person-profile ``LinkedIn``.
    """
    website = _text(row, "Website")
    employees = _headcount(row.get("Employees"))
    return {
        "name": _text(row, "Company"),
        "website": website,
        "domain": _clean_domain(website),
        "industry": _text(row, "Industry"),
        "employee_count": employees,
        "company_size": _size_band(employees),
        "city": _text(row, "City"),
        "country": _text(row, "Country"),
        "technologies": _as_list(row.get("Technologies")),
        "linkedin_url": _text(row, "Company LinkedIn"),
        "source": source,
    }


def _contact_from_contacts(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Full Name … LinkedIn`` -> a ``contacts`` payload.

    This file carries no company attributes, so ``Company`` is only a link
    target: it goes to ``company_name`` and is resolved during the load.
    """
    full_name = _text(row, "Full Name")
    first_name, last_name = _split_name(full_name)
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": _text(row, "Job Title"),
        "department": _text(row, "Department"),
        "seniority": _text(row, "Seniority"),
        "email": _email(row.get("Email")),
        "phone": _phone(row.get("Phone")),
        "linkedin_url": _text(row, "LinkedIn"),
        "company_name": _text(row, "Company"),
        "source": source,
    }


def _company_from_research(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Company Name … Company Staff Count`` -> a ``companies`` payload.

    Deliberately not read, because the schema has no home for them and
    inventing one would fabricate data: ``Company Annual Revenue``,
    ``Company Revenue Range``, ``Company Street 1-3``/``Company Post Code``,
    ``Company Phone 1-10``, ``SIC Code``, ``NAICS Code``, ``Company County``
    and the ``… Total AI`` confidence scores. ``Company Description`` does map
    - ``companies.notes`` is free text.
    """
    # The cleaned name is the de-duplicated one; fall back to the raw column.
    name = _text(row, "Company Name - Cleaned") or _text(row, "Company Name")
    # Two columns hold the host: ``Website`` (the link) and
    # ``Company Website Domain`` (the parsed host). Prefer the parsed one.
    domain = _clean_domain(row.get("Company Website Domain")) or _clean_domain(row.get("Website"))
    employees = _headcount(row.get("Company Staff Count"))
    return {
        "name": name,
        "website": _absolute_url(domain),
        "domain": domain,
        "industry": _text(row, "Company Industry"),
        "employee_count": employees,
        "company_size": _size_band(employees),
        "city": _text(row, "Company City"),
        "state": _text(row, "Company State"),
        "country": _text(row, "Company Country"),
        "founded_year": _year(row.get("Company Founded Date")),
        # The company *page*, not a person's profile.
        "linkedin_url": _text(row, "Company LI Profile Url"),
        "notes": _text(row, "Company Description"),
        "source": source,
    }


def _contact_from_research(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Contact Full Name … Contact Country`` -> a ``contacts`` payload.

    Reads only the unique ``Contact Full Name``: the header's two
    ``First Name`` and two ``Last Name`` columns collapse under
    ``csv.DictReader``, so relying on them would be luck, not a mapping.

    Not read: ``Contact State`` (``contacts`` has no state column - only
    ``companies`` does), the nine alternate ``Email 2-10`` addresses and
    ``Personal Email*`` (``contacts`` holds one address; the alternate tables
    are not rendered anywhere), ``Former Position`` / ``Time in Current …``
    (the export never says which employer the former title belonged to, and
    guessing would put a company on a role that may predate it), and every
    ``* Validation`` / ``* Total AI`` column.

    Validation columns are ignored on purpose: V-Base only ever labels an
    address verified when a ``verification_events`` row recorded it, and a
    source file's opinion is not that.
    """
    full_name = _text(row, "Contact Full Name")
    first_name, last_name = _split_name(full_name)
    # ``Primary Email`` is the curated address; ``Email 1`` is the first of the
    # scored alternates and is only used when there is no primary one.
    email = _email(row.get("Primary Email")) or _email(row.get("Email 1"))
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": _text(row, "Title"),
        "department": _text(row, "Department"),
        "seniority": _text(row, "Seniority"),
        "email": email,
        "phone": _phone(row.get("Contact Phone 1")) or _phone(row.get("Contact Mobile Phone")),
        "linkedin_url": _text(row, "Contact LI Profile URL"),
        "company_name": _text(row, "Company Name - Cleaned") or _text(row, "Company Name"),
        "city": _text(row, "Contact City"),
        "country": _text(row, "Contact Country"),
        "source": source,
    }


def _company_from_research_slim(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Company Name … Company Industry`` -> a ``companies`` payload.

    Same entity as ``_company_from_research`` but this export has no
    ``Company Staff Count`` and no ``Company State``, so headcount, size band
    and state stay whatever an earlier file already established. Its extra
    ``Job Postings`` / ``SEO Research`` / ``Wikipedia`` columns are research
    links with no column to live in, so they are skipped rather than jammed
    into ``notes``.
    """
    name = _text(row, "Company Name - Cleaned") or _text(row, "Company Name")
    domain = _clean_domain(row.get("Company Website Domain")) or _clean_domain(row.get("Website"))
    return {
        "name": name,
        "website": _absolute_url(domain),
        "domain": domain,
        "industry": _text(row, "Company Industry"),
        "city": _text(row, "Company City"),
        "country": _text(row, "Company Country"),
        "founded_year": _year(row.get("Company Founded Date")),
        "linkedin_url": _text(row, "Company LI Profile Url"),
        "notes": _text(row, "Company Description"),
        "source": source,
    }


def _contact_from_research_slim(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Contact Full Name … Contact Country`` -> a ``contacts`` payload.

    No ``Department``, ``Seniority`` or ``Contact City`` in this export -
    those come from the wider one. ``Contact State`` still has nowhere to go.
    """
    full_name = _text(row, "Contact Full Name")
    first_name, last_name = _split_name(full_name)
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": _text(row, "Title"),
        "email": _email(row.get("Primary Email")) or _email(row.get("Email 1")),
        "phone": _phone(row.get("Contact Phone 1")) or _phone(row.get("Contact Mobile Phone")),
        "linkedin_url": _text(row, "Contact LI Profile URL"),
        "company_name": _text(row, "Company Name - Cleaned") or _text(row, "Company Name"),
        "country": _text(row, "Contact Country"),
        "source": source,
    }


def _company_from_leads(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``Company Name … Jobcount`` -> a ``companies`` payload.

    ``Company Location`` is a *country* in this export (51 of 52 rows read
    "United States"), so it maps to ``country`` and not ``city`` - treating it
    as a city would have poisoned the cities chart.

    Skipped: ``Latest Funding`` (a raw dollar amount, but ``funding_stage`` is
    a stage label such as "Series A", and the schema has no funding-amount
    column), ``Jobcount`` (open roles, not headcount) and the ``Open Job *``
    columns (an unfilled vacancy, not this person's title).
    """
    domain = _clean_domain(row.get("Company Domain"))
    return {
        "name": _text(row, "Company Name"),
        "website": _absolute_url(domain),
        "domain": domain,
        "country": _text(row, "Company Location"),
        "linkedin_url": _text(row, "Company LinkedIn URL"),
        "source": source,
    }


def _contact_from_leads(row: dict[str, Any], source: str) -> dict[str, Any]:
    """``First Name … Lead LinkedIn`` -> a ``contacts`` payload.

    This export has no email, so every row falls through to the
    name-within-company match during the load. ``Open Job Title`` is a
    vacancy the company is hiring for, not this person's title - only
    ``Lead Title`` is theirs.
    """
    first_name = _text(row, "First Name")
    last_name = _text(row, "Last Name")
    full_name = " ".join(part for part in (first_name, last_name) if part) or None
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": _text(row, "Lead Title"),
        "linkedin_url": _text(row, "Lead LinkedIn"),
        "company_name": _text(row, "Company Name"),
        "city": _city_from(row.get("Location")),
        "source": source,
    }


#: (phase, kind) -> transform. Explicit, so a new file type has to be wired in
#: here rather than silently falling through a generic branch.
TRANSFORMS: dict[tuple[Phase, Kind], Any] = {
    ("companies", "wide"): _company_from_wide,
    ("contacts", "wide"): _contact_from_wide,
    ("companies", "companies"): _company_from_companies,
    ("contacts", "contacts"): _contact_from_contacts,
    ("companies", "research"): _company_from_research,
    ("contacts", "research"): _contact_from_research,
    ("companies", "research_slim"): _company_from_research_slim,
    ("contacts", "research_slim"): _contact_from_research_slim,
    ("companies", "leads"): _company_from_leads,
    ("contacts", "leads"): _contact_from_leads,
}


# ---------------------------------------------------------------------------
# Extraction - read files and match them to a declaration
# ---------------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_header(path: Path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            return tuple(cell.strip() for cell in next(reader))
        except StopIteration:
            return ()


def _iter_rows(path: Path) -> Any:
    """Yield rows one at a time.

    Deliberately a generator: the research export is ~48 MB and materialising
    all 173 columns of 22,903 rows at once costs hundreds of megabytes for no
    benefit, since the transform consumes and discards one row at a time.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def discover(directory: Path, only: set[str] | None = None) -> Discovery:
    """Classify every CSV in ``directory`` against the column declarations.

    Files are deduplicated by content first, so a re-export of the same bytes
    is reported rather than loaded twice.
    """
    result = Discovery()
    seen: dict[str, Path] = {}

    for path in sorted(directory.glob("*.csv")):
        if only and path.name not in only:
            continue
        try:
            digest = _digest(path)
        except OSError:  # pragma: no cover - unreadable input
            logger.warning("Cannot read %s; skipping", path)
            continue

        if digest in seen:
            result.duplicates.append((path, seen[digest]))
            continue

        columns = _read_header(path)
        kind = COLUMNS_BY_KIND.get(columns)
        if kind is None:
            result.unrecognised.append(path)
            continue

        seen[digest] = path
        result.specs.append(FileSpec(path=path, columns=columns, kind=kind, phases=PHASES_BY_KIND[kind], digest=digest))
    return result


# ---------------------------------------------------------------------------
# Load - idempotent upserts
# ---------------------------------------------------------------------------


@dataclass
class _Lookup:
    """In-memory identity index, keyed exactly the way the tables are.

    The research export repeats ~9,400 employers across 22,903 rows. Without
    this the load would issue two indexed queries per row (~45,000 round
    trips); with it there is at most one query per distinct key, and every
    later row for the same company or person is answered from memory.
    """

    companies_by_domain: dict[str, Company] = field(default_factory=dict)
    companies_by_name: dict[str, Company] = field(default_factory=dict)
    contacts_by_email: dict[str, Contact] = field(default_factory=dict)
    contacts_by_person: dict[tuple[str, int | None], Contact] = field(default_factory=dict)

    def remember_company(self, company: Company) -> None:
        if company.domain:
            self.companies_by_domain[company.domain] = company
        if company.name:
            self.companies_by_name[company.name.lower()] = company

    def remember_contact(self, contact: Contact) -> None:
        if contact.email:
            self.contacts_by_email[contact.email.lower()] = contact
        if contact.full_name:
            self.contacts_by_person[(contact.full_name.lower(), contact.company_id)] = contact


async def _find_company(session, payload: dict[str, Any], lookup: _Lookup) -> Company | None:
    """Match on the derived domain first, then on a case-insensitive name."""
    domain = payload.get("domain")
    if domain:
        cached = lookup.companies_by_domain.get(domain)
        if cached is not None:
            return cached
        row = (await session.execute(select(Company).where(Company.domain == domain).limit(1))).scalar_one_or_none()
        if row is not None:
            lookup.remember_company(row)
            return row

    name = payload.get("name")
    if name:
        name_key = name.lower()
        cached = lookup.companies_by_name.get(name_key)
        if cached is not None:
            return cached
        row = (
            await session.execute(select(Company).where(func.lower(Company.name) == name_key).limit(1))
        ).scalar_one_or_none()
        if row is not None:
            lookup.remember_company(row)
            return row
    return None


@lru_cache(maxsize=8)
def _limits(model: Any) -> dict[str, int | None]:
    """Column name -> declared string length, read off the model itself.

    Stating the limits here would let a migration and the ETL drift apart;
    asking the SQLAlchemy column means the schema is the only source of truth.
    """
    return {name: getattr(column.type, "length", None) for name, column in model.__table__.columns.items()}


def _clamp(payload: dict[str, Any], model: Any) -> tuple[dict[str, Any], int]:
    """Shorten strings that would exceed their column.

    Research exports carry free-text fields such as ``Company Description``
    and job titles scraped from long postings; a value one character over a
    ``VARCHAR(n)`` aborts the whole load with a DataError. Truncating to the
    model's own declared length keeps the row and is counted so the loss is
    visible in the report.
    """
    limits = _limits(model)
    shortened = 0
    out: dict[str, Any] = {}
    for key, value in payload.items():
        limit = limits.get(key)
        if isinstance(value, str) and limit and len(value) > limit:
            out[key] = value[:limit]
            shortened += 1
        else:
            out[key] = value
    return out, shortened


def _has_value(target: Any, key: str, value: Any) -> bool:
    """True when ``target`` already holds a meaningful value for ``key``.

    ``None`` entries are never written, so it is also what keeps a source
    file that simply does not carry a column from erasing it.

    ``value`` is passed in so empty strings and empty lists are treated as
    missing too, not as present values that should overwrite the target.
    """
    current = getattr(target, key, None)
    if current is None:
        return False
    if current == "" or current == []:
        return False
    if isinstance(current, str) and current.strip() == "":
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _merge(target: Any, payload: dict[str, Any], overwrite: bool) -> bool:
    """Fill empty fields on ``target``; replace them only with ``overwrite``.

    Explicit, not implicit: a value is written only when a payload column is
    present. An earlier file's website must never be blanked by a later
    person-only file that drops it, and a re-run of the same file must never
    silently overwrite what it already wrote.

    ``overwrite=True`` replaces every populated field, like a full re-import.
    """
    changed = False
    for key, value in payload.items():
        if value is None:
            continue
        if not _has_value(target, key, value):
            setattr(target, key, value)
            changed = True
        elif overwrite:
            setattr(target, key, value)
            changed = True
    return changed


async def _upsert_company(
    session,
    payload: dict[str, Any],
    *,
    overwrite: bool,
    report: FileReport,
    touched: set[int],
    lookup: _Lookup,
) -> Company:
    payload, shortened = _clamp(payload, Company)
    report.truncated += shortened
    company = await _find_company(session, payload, lookup)
    if company is None:
        company = Company(**{k: v for k, v in payload.items() if v is not None})
        company.data_quality_score = _company_quality(payload)
        session.add(company)
        report.created += 1
    if overwrite:
        report.updated += 1
    elif _merge(company, payload, overwrite):
        report.updated += 1
    else:
        report.unchanged += 1

    await session.flush()
    lookup.remember_company(company)
    touched.add(company.id)
    return company


async def _find_contact(session, payload: dict[str, Any], lookup: _Lookup) -> Contact | None:
    """Match on email, else on the person's name within their company.

    The company is read from ``payload`` because ``_upsert_contact`` resolves
    the link before asking, so name-only matches are never confused with a
    namesake at another employer.
    """
    email = payload.get("email")
    if email:
        cached = lookup.contacts_by_email.get(email)
        if cached is not None:
            return cached
        row = (
            await session.execute(select(Contact).where(func.lower(Contact.email) == email).limit(1))
        ).scalar_one_or_none()
        if row is not None:
            lookup.remember_contact(row)
            return row

    full_name = payload.get("full_name")
    if full_name:
        company_id = payload.get("company_id")
        name_key = full_name.lower()
        cached = lookup.contacts_by_person.get((name_key, company_id))
        if cached is not None:
            return cached
        stmt = select(Contact).where(func.lower(Contact.full_name) == name_key)
        if company_id is not None:
            stmt = stmt.where(Contact.company_id == company_id)
        row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
        if row is not None:
            lookup.remember_contact(row)
            return row
    return None


async def _resolve_company(
    session, company_name: str | None, report: FileReport, touched: set[int], lookup: _Lookup
) -> Company | None:
    """Find the company a contact should link to, creating a stub if needed.

    A person-only export has no company attributes, so an unknown employer
    becomes a name-only stub rather than an orphaned contact. The stub is
    reported so the gap is visible instead of hidden.
    """
    if not company_name:
        return None
    company = await _find_company(session, {"name": company_name}, lookup)
    if company is not None:
        touched.add(company.id)
        return company

    company = Company(name=company_name)
    session.add(company)
    await session.flush()
    lookup.remember_company(company)
    touched.add(company.id)
    report.companies_created_for_contacts += 1
    return company


async def _upsert_contact(
    session,
    payload: dict[str, Any],
    *,
    company: Company | None,
    overwrite: bool,
    report: FileReport,
    lookup: _Lookup,
) -> Contact:
    if company is not None:
        await session.flush()
        payload["company_id"] = company.id
        payload["company_name"] = payload.get("company_name") or company.name

    payload, shortened = _clamp(payload, Contact)
    report.truncated += shortened

    contact = await _find_contact(session, payload, lookup)
    if contact is None:
        contact = Contact(**{k: v for k, v in payload.items() if v is not None})
        contact.data_quality_score = _contact_quality(payload)
        session.add(contact)
        report.created += 1
        await session.flush()
    elif _merge(contact, payload, overwrite):
        report.updated += 1
    else:
        report.unchanged += 1

    lookup.remember_contact(contact)
    return contact


async def _rescore_companies(session, ids: set[int]) -> int:
    """Recompute company scores now that their contacts exist.

    ``_company_quality`` awards up to 15 points for linked contacts, which
    cannot be known until the contacts phase has run, so scoring happens once
    more here over the same grouped count the list endpoint uses.

    The score is built from a dict rather than the ORM instance: passing a
    ``Company`` makes ``_company_quality`` touch ``data.contacts``, and reading
    that lazy relationship inside an async session raises ``MissingGreenlet``.
    The dict is the same field set used when the row was first scored, so the
    rescan can only add the contact bonus - never erase the base score.
    """
    if not ids:
        return 0
    rows = await session.execute(select(Company).where(Company.id.in_(ids)).execution_options(populate_existing=True))
    companies = rows.scalars().all()
    counts = dict(
        (
            await session.execute(
                select(Contact.company_id, func.count(Contact.id))
                .where(Contact.company_id.in_(ids))
                .group_by(Contact.company_id)
            )
        ).all()
    )
    for company in companies:
        base = _company_quality(
            {
                "name": company.name,
                "website": company.website,
                "domain": company.domain,
                "linkedin_url": company.linkedin_url,
                "industry": company.industry,
                "city": company.city,
                "country": company.country,
                "employee_count": company.employee_count,
                "founded_year": company.founded_year,
                "technologies": company.technologies,
            }
        )
        company.data_quality_score = min(100, base + min(15, counts.get(company.id, 0) * 3))
    return len(companies)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _process_file(
    session,
    spec: FileSpec,
    phase: Phase,
    report: FileReport,
    *,
    overwrite: bool,
    dry_run: bool,
    touched: set[int],
    lookup: _Lookup,
) -> None:
    transform = TRANSFORMS.get((phase, spec.kind))
    if transform is None:
        return

    rows = _iter_rows(spec.path)
    source = spec.path.name

    for row in rows:
        payload = transform(row, source)
        if phase == "companies":
            if not payload.get("name"):
                continue
            report.rows += 1
            await _upsert_company(session, payload, overwrite=overwrite, report=report, touched=touched, lookup=lookup)
            continue

        if not payload.get("full_name") and not payload.get("email"):
            continue
        report.rows += 1
        company = await _resolve_company(session, payload.get("company_name"), report, touched, lookup)
        await _upsert_contact(session, payload, company=company, overwrite=overwrite, report=report, lookup=lookup)

    if dry_run:
        # The whole run is rolled back at the end; flushing here only makes the
        # counts and the company links real enough to report accurately.
        await session.flush()


async def run_etl(
    directory: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
    only: set[str] | None = None,
) -> tuple[list[FileReport], Discovery, int]:
    """Extract, transform and load.

    Returns ``(per-file reports, discovery, companies rescored)``. A ``wide``
    file contributes to both phases but is reported once, with both passes
    accumulating into the same row.
    """
    discovery = discover(directory, only)
    reports_by_path: dict[Path, FileReport] = {}
    touched: set[int] = set()
    lookup = _Lookup()

    async with session_scope() as session:
        for phase in ("companies", "contacts"):
            for spec in discovery.specs:
                if phase not in spec.phases:
                    continue
                report = reports_by_path.get(spec.path)
                if report is None:
                    report = FileReport(path=spec.path, kind=spec.kind)
                    reports_by_path[spec.path] = report
                await _process_file(
                    session,
                    spec,
                    phase,
                    report,
                    overwrite=overwrite,
                    dry_run=dry_run,
                    touched=touched,
                    lookup=lookup,
                )

        rescored = await _rescore_companies(session, touched)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return list(reports_by_path.values()), discovery, rescored


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_discovery(discovery: Discovery) -> None:
    if discovery.specs:
        print("Recognised files")
        print(f"  {'file':<44} {'kind':<11} columns")
        for spec in discovery.specs:
            print(f"  {spec.path.name:<44} {spec.kind:<11} {len(spec.columns)}")

    for path, original in discovery.duplicates:
        print(f"  skipped (identical to {original.name}): {path.name}")

    for path in discovery.unrecognised:
        try:
            columns = ", ".join(_read_header(path)) or "<empty>"
        except OSError:  # pragma: no cover
            columns = "<unreadable>"
        print(f"  UNHANDLED {path.name}: header not declared -> {columns}")


def _print_reports(reports: list[FileReport], dry_run: bool, rescored: int) -> None:
    if reports:
        print()
        print("Load")
        print(f"  {'file':<44} {'kind':<11} {'rows':>5} {'new':>5} {'upd':>5} {'same':>5}")
        for report in reports:
            print(
                f"  {report.path.name:<44} {report.kind:<11} {report.rows:>5} "
                f"{report.created:>5} {report.updated:>5} {report.unchanged:>5}"
            )

    totals = {
        key: sum(getattr(report, key) for report in reports)
        for key in (
            "rows",
            "created",
            "updated",
            "unchanged",
            "companies_created_for_contacts",
            "truncated",
        )
    }
    print()
    print(
        f"  rows={totals['rows']} created={totals['created']} "
        f"updated={totals['updated']} unchanged={totals['unchanged']} "
        f"stub_companies={totals['companies_created_for_contacts']}"
    )
    if totals["truncated"]:
        print(
            f"  {totals['truncated']} value(s) shortened to fit their column "
            "(length limits read from the SQLAlchemy models)"
        )
    if rescored:
        print(f"  rescanned {rescored} companies for contact-count quality scores")
    if dry_run:
        print("  DRY RUN - everything above was rolled back")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vbase-etl",
        description="Load the CSV exports in uploads/ into the unified PostgreSQL schema",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="Show which files are recognised and which are not")
    listing.add_argument("--dir", type=Path, default=None, help="Directory to scan (default: uploads)")
    listing.add_argument("--file", action="append", default=None, help="Only consider this file name")

    run = sub.add_parser("run", help="Extract, transform and load")
    run.add_argument("--dir", type=Path, default=None, help="Directory to scan (default: uploads)")
    run.add_argument("--file", action="append", default=None, help="Only consider this file name")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute the whole load and roll it back, so the report is accurate",
    )
    run.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace fields that already hold a value instead of only filling blanks",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = args.dir or settings.uploads_dir
    if not directory.exists():
        print(f"No such directory: {directory}", file=sys.stderr)
        return 2

    only = set(args.file) if args.file else None
    if only:
        missing = sorted(name for name in only if not (directory / name).exists())
        if missing:
            print(f"Not in {directory}: {', '.join(missing)}", file=sys.stderr)
            return 2

    if args.command == "list":
        discovery = discover(directory, only)
        _print_discovery(discovery)
        return 0 if discovery.specs else 1

    reports, discovery, rescored = _run_sync(
        directory,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        only=only,
    )

    print(f"ETL - {directory}")
    _print_discovery(discovery)
    _print_reports(reports, args.dry_run, rescored)

    if not discovery.specs:
        return 1
    if discovery.unrecognised:
        print(
            f"\n{len(discovery.unrecognised)} file(s) were skipped because their "
            "columns are not declared. Add a column tuple and a transform to handle them.",
            file=sys.stderr,
        )
    return 0


def _run_sync(directory: Path, *, dry_run: bool, overwrite: bool, only: set[str] | None):
    """Run the async loader from the synchronous CLI entry point."""
    import asyncio

    return asyncio.run(run_etl(directory, dry_run=dry_run, overwrite=overwrite, only=only))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
