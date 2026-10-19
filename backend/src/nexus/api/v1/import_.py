from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity
from nexus.core.config import settings
from nexus.core.db import get_session
from nexus.core.exceptions import BadRequestError, ImportError
from nexus.core.phones import canonical_for_matching, normalize_phone
from nexus.database import (
    Company,
    Contact,
    CustomField,
    CustomFieldValue,
    DuplicateCandidate,
    ImportErrorRow,
    ImportJob,
    ImportRow,
)

router = APIRouter(tags=["import"])
logger = logging.getLogger(__name__)

_MAX_PREVIEW_ROWS = 100
_MAX_PREVIEW_COLS = 60
#: Rows applied between commits. Each committed batch keeps the progress
#: endpoint live (rows added so far are visible while the run continues). Rows
#: the database rejects are flagged and skipped — only a connection-level
#: failure would give up the uncommitted batch.
_FLUSH_EVERY = 25

#: Row-level import behaviour.
STRATEGIES = {
    "add": "Only insert new records; rows matching an existing record are skipped.",
    "update": "Only update existing records; rows with no match are skipped.",
    "add_and_update": "Insert new records and update existing ones.",
    "skip_duplicates": "Insert new records; anything matching an existing record is left untouched.",
}

#: How an update treats a column that already holds a value.
UPDATE_MODES = {
    "fill_empty": "Only fill blank fields; never overwrite a value that already exists.",
    "overwrite": "Replace existing values, recording every change in the preview and audit log.",
}

#: Fields a normalised import row may write.
_COMPANY_FIELDS = (
    "name",
    "website",
    "domain",
    "linkedin_url",
    "industry",
    "sub_industry",
    "employee_count",
    "company_size",
    "country",
    "state",
    "city",
    "headquarters",
    "founded_year",
    "technologies",
    "funding_stage",
    "company_status",
    "source",
    "notes",
)
_CONTACT_FIELDS = (
    "first_name",
    "last_name",
    "full_name",
    "job_title",
    "department",
    "seniority",
    "email",
    "email_status",
    "phone",
    "phone_status",
    "linkedin_url",
    "company_name",
    "city",
    "country",
    "skills",
    "employment_history",
    "source",
    "notes",
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@router.get("/import/options")
async def import_options():
    """Strategies and update modes the wizard offers."""
    return {
        "strategies": [{"value": k, "description": v} for k, v in STRATEGIES.items()],
        "update_modes": [{"value": k, "description": v} for k, v in UPDATE_MODES.items()],
        # Mapping vocabulary. Company rows address their name as
        # ``company_name`` so a single mapping works for rows that also name a
        # contact's employer.
        "target_fields": {
            "company": ["company_name", *_COMPANY_FIELDS[1:]],
            "contact": list(_CONTACT_FIELDS),
        },
        # Any other column can target a custom field, one per column:
        # ``custom:contact:Field Name`` or ``custom:company:Field Name``.
        # Missing definitions are created as text fields on import.
        "custom_target_format": "custom:<contact|company>:<Field Name>",
        "max_upload_bytes": settings.max_upload_bytes,
        "allowed_extensions": list(settings.allowed_upload_extensions),
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/import/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    ext = _file_extension(file.filename or "")
    if ext not in settings.allowed_upload_extensions:
        raise BadRequestError(
            f"Unsupported file type: {ext or 'unknown'}. Allowed: {', '.join(settings.allowed_upload_extensions)}"
        )

    content = await file.read()
    if not content:
        raise BadRequestError("The uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise BadRequestError(f"File too large. Maximum: {settings.max_upload_bytes // (1024 * 1024)}MB")
    _validate_signature(ext, content)

    file_hash = hashlib.sha256(content).hexdigest()
    prefix = uuid.uuid4().hex
    safe_name = f"{prefix}{ext}"
    dest = settings.uploads_path / safe_name
    dest.write_bytes(content)

    # Reading the workbook here means an unreadable file is rejected at upload
    # time instead of failing half way through an import.
    try:
        sheets = _sheet_names(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ImportError(f"Could not read the file: {exc}") from exc

    job = ImportJob(
        filename=(file.filename or "upload")[:300],
        file_mime=file.content_type,
        file_size_bytes=len(content),
        file_hash=file_hash,
        status="uploaded",
        file_path=str(dest),
        sheet_names=sheets,
        sheet_name=sheets[0] if sheets else None,
        mapping={},
        created_by_id=current_user.id,
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)
    await session.commit()

    return {
        "job_id": job.id,
        "filename": job.filename,
        "file_size_bytes": job.file_size_bytes,
        "status": job.status,
        "sheet_names": job.sheet_names or [],
        "default_sheet": job.sheet_name,
        "is_spreadsheet": _is_spreadsheet(job.filename, job.file_mime),
    }


@router.get("/import/sheets/{job_id}")
async def list_sheets(
    job_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    job = await _owned_job(session, job_id, current_user.id)
    sheets = _sheet_names(Path(job.file_path)) if job.file_path else []
    return {"job_id": job.id, "sheets": sheets, "selected": job.sheet_name}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@router.get("/import/preview/{job_id}")
async def preview_import(
    job_id: int,
    sheet: str | None = Query(None, max_length=200),
    limit: int = Query(_MAX_PREVIEW_ROWS, ge=1, le=_MAX_PREVIEW_ROWS),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    job = await _owned_job(session, job_id, current_user.id)
    path = _job_path(job)
    if sheet and sheet != job.sheet_name:
        job.sheet_name = sheet
        await session.commit()

    try:
        df = _read_table(path, job, sheet=sheet, nrows=limit)
    except Exception as exc:
        raise ImportError(f"Could not preview file: {exc}") from exc

    df.columns = _unique_columns([str(c).strip() for c in df.columns])
    columns = list(df.columns)[:_MAX_PREVIEW_COLS]
    rows = [{str(col): _coerce_value(row[col]) for col in columns} for _, row in df.head(limit).iterrows()]

    total_rows = _count_rows(path, job, sheet=sheet)
    return {
        "job_id": job.id,
        "filename": job.filename,
        "sheet_name": sheet or job.sheet_name,
        "sheet_names": job.sheet_names or [],
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "col_count": len(columns),
        "total_rows_estimate": total_rows,
        "suggested_mapping": suggest_mapping(columns),
    }


@router.post("/import/mapping/{job_id}")
async def set_mapping(
    job_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Persist the wizard's mapping, import strategy and update mode."""
    job = await _owned_job(session, job_id, current_user.id)

    mapping = body.get("mapping")
    if isinstance(mapping, dict):
        allowed = set(_COMPANY_FIELDS) | set(_CONTACT_FIELDS) | {"company_name"}
        unknown = sorted(
            {str(v) for v in mapping.values() if v}
            - allowed
            - {str(v) for v in mapping.values() if v and _parse_custom_target(str(v)) is not None}
        )
        if unknown:
            raise BadRequestError(
                f"Unknown target field(s): {', '.join(unknown)}. See /import/options for the vocabulary."
            )
        job.mapping = {str(k): str(v) for k, v in mapping.items() if v}

    strategy = body.get("strategy")
    if strategy is not None:
        if strategy not in STRATEGIES:
            raise BadRequestError(f"Unknown strategy '{strategy}'. Valid: {', '.join(STRATEGIES)}")
        job.strategy = strategy

    update_mode = body.get("update_mode")
    if update_mode is not None:
        if update_mode not in UPDATE_MODES:
            raise BadRequestError(f"Unknown update_mode '{update_mode}'. Valid: {', '.join(UPDATE_MODES)}")
        job.update_mode = update_mode

    sheet = body.get("sheet_name")
    if sheet:
        job.sheet_name = str(sheet)[:200]

    job.status = "mapped"
    await session.commit()
    await session.refresh(job)
    return {
        "job_id": job.id,
        "mapping": job.mapping,
        "strategy": job.strategy,
        "update_mode": job.update_mode,
        "sheet_name": job.sheet_name,
        "status": job.status,
    }


# ---------------------------------------------------------------------------
# Dry run (field-level preview)
# ---------------------------------------------------------------------------


@router.get("/import/plan/{job_id}")
async def import_plan(
    job_id: int,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Dry run: classify every row and show the exact field changes.

    Nothing is written. This is what the wizard shows before the user commits,
    and it is the guarantee behind "never overwrite existing values silently".

    This is O(number of bulk queries), not O(rows × queries): all rows in the
    file are matched in memory against a handful of chunked ``IN`` queries,
    instead of issuing two-or-more sequential queries per row. The decision
    logic is identical to ``_plan_row``; the dry-run samples up to ``limit``
    items evenly across the whole file while the counts cover every row.
    """
    job = await _owned_job(session, job_id, current_user.id)
    df = await run_in_threadpool(_load_frame, job)
    total_rows = int(df.shape[0])

    counts = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0, "invalid": 0, "duplicate": 0}
    plan_rows: list[tuple[int, tuple[str, Any]]] = []
    invalid_items_shown = 0

    for idx, row in df.iterrows():
        raw_row = {str(col): _coerce_value(row[col]) for col in df.columns}
        normalized = _normalize_row(raw_row, job.mapping or {})
        if not normalized:
            counts["invalid"] += 1
            if invalid_items_shown < limit:
                plan_rows.append(
                    (idx, ("inv", {"action": "invalid", "entity": None, "reason": "No mapped values", "changes": {}}))
                )
                invalid_items_shown += 1
            continue
        plan_rows.append((idx, ("row", normalized)))

    contact_email_map, contact_name_map, contact_fl_map = await _bulk_load_contacts(session, plan_rows)
    company_domain_map, company_name_map = await _bulk_load_companies(session, plan_rows)
    custom_fields_map = await _bulk_load_custom_fields(session)
    contact_ids: set[int] = set()
    company_ids: set[int] = set()

    def _resolve(entry: tuple[str, Any]) -> tuple[str, Any, dict[str, Any]] | None:
        """Returns (entity, existing, normalized) for a valid row, else None."""
        tag, payload = entry
        if tag != "row":
            return None
        normalized: dict[str, Any] = payload
        entity = "company" if _looks_like_company(normalized) else ("contact" if _looks_like_contact(normalized) else None)
        if entity is None:
            return None
        if entity == "contact":
            existing = _match_contact_locally(normalized, contact_email_map, contact_name_map, contact_fl_map)
        else:
            existing = _match_company_locally(normalized, company_domain_map, company_name_map)
        if existing is not None:
            (contact_ids if entity == "contact" else company_ids).add(existing.id)
        return entity, existing, normalized

    custom_values = await _bulk_load_custom_values(session, contact_ids, company_ids)

    for _idx, _entry in plan_rows:
        resolved = _resolve(_entry)
        if resolved is None:
            continue
        entity, existing, normalized = resolved
        plan = _plan_action_locally(
            existing, entity, normalized, job.strategy, job.update_mode,
            custom_fields_map, custom_values,
        )
        counts[plan["action"]] = counts.get(plan["action"], 0) + 1

    def _item(idx: int, plan: dict[str, Any]) -> dict[str, Any]:
        item: dict[str, Any] = {
            "row_index": int(idx),
            "action": plan["action"],
            "changes": plan.get("changes") or {},
            "reason": plan.get("reason"),
        }
        if plan.get("entity"):
            item["entity"] = plan["entity"]
        if plan.get("duplicate_of") is not None:
            item["duplicate_of"] = plan["duplicate_of"]
        return item

    # Planned decisions per row (plain dict for 'row' entries), in file order.
    decided: list[tuple[int, tuple[str, Any]]] = []
    for idx, entry in plan_rows:
        tag, payload = entry
        if tag == "inv":
            decided.append((idx, entry))
            continue
        resolved = _resolve(entry)
        if resolved is None:
            continue
        entity, existing, normalized = resolved
        plan = _plan_action_locally(
            existing, entity, normalized, job.strategy, job.update_mode,
            custom_fields_map, custom_values,
        )
        decided.append((idx, ("inv", plan)))  # reuse 'inv' tag: a dict payload = ready plan

    # Evenly sample up to `limit` items across the whole file so the review
    # page stays representative and constant-sized no matter the row count.
    keep = min(limit, len(decided))
    if keep == 0:
        items: list[dict[str, Any]] = []
    else:
        step = len(decided) / keep
        picked = {min(int(i * step), len(decided) - 1) for i in range(keep)}
        items = [_item(decided[i][0], decided[i][1][1]) for i in sorted(picked)]

    return {
        "job_id": job.id,
        "strategy": job.strategy,
        "update_mode": job.update_mode,
        "rows_total": total_rows,
        "previewed": len(items),
        "counts": counts,
        "items": items,
        "truncated": total_rows > len(items),
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@router.post("/import/run/{job_id}")
async def run_import(
    job_id: int,
    allow_duplicate_creates: bool = Query(
        False,
        description="When true, a row that looks like a duplicate of an existing record is "
        "still inserted and flagged for review instead of being skipped.",
    ),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Apply the import row by row, in batched commits, continuing past bad rows.

    Every row is planned first (same code path as ``/import/plan``), then rows
    are applied and committed every ``_FLUSH_EVERY`` rows. Each row's writes run
    inside a savepoint, so a row the database rejects is flagged in the error
    report and the run keeps going instead of stopping. Each completed batch is
    durable and visible to ``/import/progress`` immediately, so the live
    counters show how many rows have actually been written while the run is
    still going. An unexpected (non-row) failure rolls back only the in-flight
    batch; the rows committed before it stay saved.
    """
    job = await _owned_job(session, job_id, current_user.id)

    # _load_frame re-validates the upload path and reads the mapping, so an
    # import with no mapping fails here rather than half way through.
    df = await run_in_threadpool(_load_frame, job)
    job.status = "running"
    job.started_at = _utcnow()
    job.rows_total = int(df.shape[0])
    job.rows_processed = 0
    job.error_summary = None
    # Clears any previous attempt so a re-run is not additive.
    await session.execute(ImportErrorRow.__table__.delete().where(ImportErrorRow.import_job_id == job.id))
    await session.execute(ImportRow.__table__.delete().where(ImportRow.import_job_id == job.id))
    await session.commit()

    counters = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "invalid": 0,
        "duplicate": 0,
    }

    # Preload every matching candidate in a handful of bulk queries — the run
    # must not do 2+ sequential queries per row or large files take minutes.
    plan_rows: list[tuple[int, tuple[str, Any], dict[str, Any]]] = []
    for idx, row in df.iterrows():
        raw_row = {str(col): _coerce_value(row[col]) for col in df.columns}
        normalized = _normalize_row(raw_row, job.mapping or {})
        plan_rows.append((idx, ("row", normalized) if normalized else ("inv", {}), raw_row))
    contact_email_map, contact_name_map, contact_fl_map = await _bulk_load_contacts(
        session, [(idx, e) for idx, e, _ in plan_rows]
    )
    company_domain_map, company_name_map = await _bulk_load_companies(
        session, [(idx, e) for idx, e, _ in plan_rows]
    )
    custom_fields_map = await _bulk_load_custom_fields(session)

    # Records created during THIS run must be findable by later rows without
    # re-querying the database (in-file dedupe/links stay correct).
    new_contacts_email: dict[str, Contact] = {}
    new_contacts_name: dict[str, Contact] = {}
    new_companies_domain: dict[str, Company] = {}
    new_companies_name: dict[str, Company] = {}

    def _match(normalized: dict[str, Any], entity: str):
        if entity == "contact":
            email = (normalized.get("email") or "").strip().lower()
            if email:
                hit = new_contacts_email.get(email)
                if hit is not None:
                    return hit
            full_name = (_full_name_for(normalized) or "").lower()
            if full_name:
                hit = new_contacts_name.get(full_name)
                if hit is not None:
                    return hit
            return _match_contact_locally(normalized, contact_email_map, contact_name_map, contact_fl_map)
        domain = (normalized.get("domain") or "").strip().lower().removeprefix("www.")
        host = _domain_from_url(normalized.get("website"))
        if domain and domain in new_companies_domain:
            return new_companies_domain[domain]
        if host and host in new_companies_domain:
            return new_companies_domain[host]
        name = (normalized.get("company_name") or "").strip().lower()
        if name and name in new_companies_name:
            return new_companies_name[name]
        return _match_company_locally(normalized, company_domain_map, company_name_map)

    # Custom-field value state for rows matched against PRE-EXISTING records.
    contact_ids: set[int] = set()
    company_ids: set[int] = set()
    for _idx, (tag, normalized), _raw in plan_rows:
        if tag != "row":
            continue
        _entity = "company" if _looks_like_company(normalized) else (
            "contact" if _looks_like_contact(normalized) else None
        )
        if _entity == "contact":
            if (hit := _match_contact_locally(normalized, contact_email_map, contact_name_map, contact_fl_map)):
                contact_ids.add(hit.id)
        elif _entity == "company":
            if (hit := _match_company_locally(normalized, company_domain_map, company_name_map)):
                company_ids.add(hit.id)
    custom_values = await _bulk_load_custom_values(session, contact_ids, company_ids)

    def _register(created: Any, entity: str, normalized: dict[str, Any]) -> None:
        """Make a record created during this run findable by later rows."""
        if entity == "contact":
            if created.email:
                new_contacts_email[created.email.strip().lower()] = created
            name = _full_name_for(normalized)
            if name:
                new_contacts_name[name.lower()] = created
        else:
            if created.domain:
                new_companies_domain[created.domain.strip().lower().removeprefix("www.")] = created
            if created.name:
                new_companies_name[created.name.strip().lower()] = created
            if normalized.get("company_name"):
                new_companies_name[str(normalized["company_name"]).strip().lower()] = created

    def _persist_counters(j: ImportJob, c: dict[str, int]) -> None:
        """Mirror the live counters onto the job row so batches survive a crash."""
        j.rows_added = c["added"]
        j.rows_updated = c["updated"]
        j.rows_unchanged = c["unchanged"]
        j.rows_duplicate = c["duplicate"]
        j.rows_skipped = c["skipped"]
        j.rows_invalid = c["invalid"]

    async def _flag_row_rejected(
        idx: int, raw_row: dict[str, Any], normalized: dict[str, Any], exc: Any, entity: str | None
    ) -> None:
        """After a per-row savepoint rollback: flag the row and keep going.

        Rolling back to the savepoint undid this row's writes but left the
        outer transaction usable, so the error report still lands on disk and
        the remaining rows are applied as planned.
        """
        counters["invalid"] += 1
        await session.flush()
        reason = f"Database rejected row: {type(exc).__name__}: {exc}"[:300]
        _record_row(session, job, idx, raw_row, normalized, "invalid", reason, None, entity)
        _record_error(session, job, idx, None, raw_row, reason, "error")

    try:
        for idx, (tag, normalized), raw_row in plan_rows:
            job.rows_processed = (job.rows_processed or 0) + 1

            if tag != "row":
                counters["invalid"] += 1
                _record_row(session, job, idx, raw_row, {}, "invalid", "No mapped values", None, None)
                _record_error(session, job, idx, None, None, "No mapped values", "error")
                continue

            entity = "company" if _looks_like_company(normalized) else ("contact" if _looks_like_contact(normalized) else None)
            if entity is None:
                counters["invalid"] += 1
                reason = "Could not classify row as company or contact"
                _record_row(session, job, idx, raw_row, normalized, "invalid", reason, None, None)
                _record_error(session, job, idx, None, None, reason, "error")
                continue
            existing = _match(normalized, entity)
            plan = _plan_action_locally(
                existing, entity, normalized, job.strategy, job.update_mode, custom_fields_map, custom_values
            )
            action = plan["action"]

            if action == "invalid":
                counters["invalid"] += 1
                _record_row(session, job, idx, raw_row, normalized, "invalid", plan.get("reason"), None, None)
                _record_error(session, job, idx, None, plan.get("reason"), plan.get("reason"), "error")
                continue

            if action == "skipped":
                if plan.get("duplicate_of"):
                    if allow_duplicate_creates:
                        # Explicit opt-in: insert anyway and flag for the Duplicates page.
                        # A per-row savepoint keeps a bad row from stopping the run.
                        try:
                            async with session.begin_nested():
                                created = await _apply_create(
                                    session,
                                    normalized,
                                    plan["entity"],
                                    current_user.id,
                                    company=_match({"company_name": normalized.get("company_name")}, "company")
                                    if plan["entity"] == "contact"
                                    else None,
                                )
                                await session.flush()
                                _flag_duplicate(session, plan["entity"], plan["duplicate_of"], created, plan)
                                _record_row(
                                    session,
                                    job,
                                    idx,
                                    raw_row,
                                    normalized,
                                    "duplicate",
                                    plan.get("reason"),
                                    created,
                                    plan["entity"],
                                )
                            counters["duplicate"] += 1
                            # Register only after the savepoint released — a
                            # rolled-back create must not stay findable.
                            _register(created, plan["entity"], normalized)
                        except Exception as exc:
                            await _flag_row_rejected(idx, raw_row, normalized, exc, plan["entity"])
                    else:
                        counters["skipped"] += 1
                        _record_row(
                            session, job, idx, raw_row, normalized, "skipped", plan.get("reason"), None, plan["entity"]
                        )
                        _record_error(session, job, idx, None, raw_row, plan.get("reason") or "Duplicate", "warning")
                    continue
                counters["skipped"] += 1
                _record_row(session, job, idx, raw_row, normalized, "skipped", plan.get("reason"), None, plan["entity"])
                _record_error(session, job, idx, None, raw_row, plan.get("reason") or "No matching record", "warning")
                continue

            if action == "unchanged":
                counters["unchanged"] += 1
                _record_row(
                    session,
                    job,
                    idx,
                    raw_row,
                    normalized,
                    "unchanged",
                    "All mapped fields already up to date",
                    plan.get("target"),
                    plan["entity"],
                )
                continue

            if action == "updated":
                # Per-row savepoint: one bad row is flagged, not fatal.
                try:
                    async with session.begin_nested():
                        target = plan["target"]
                        for field, change in plan["changes"].items():
                            setattr(target, field, change["to"])
                        target.data_quality_score = (
                            _company_quality(target) if plan["entity"] == "company" else _contact_quality(target)
                        )
                        await session.flush()
                        custom_written = await _apply_custom_values(
                            session, normalized, plan["entity"], target.id, current_user.id, job.update_mode
                        )
                        _record_row(
                            session,
                            job,
                            idx,
                            raw_row,
                            normalized,
                            "updated",
                            f"{len(plan['changes'])} field(s) updated"
                            + (f", {custom_written} custom field(s)" if custom_written else ""),
                            target,
                            plan["entity"],
                            update_preview=plan["changes"],
                        )
                    counters["updated"] += 1
                except Exception as exc:
                    await _flag_row_rejected(idx, raw_row, normalized, exc, plan["entity"])
                continue

            # action == "added"
            # Per-row savepoint: one bad row is flagged, not fatal.
            try:
                async with session.begin_nested():
                    created = await _apply_create(
                        session,
                        normalized,
                        plan["entity"],
                        current_user.id,
                        company=_match({"company_name": normalized.get("company_name")}, "company")
                        if plan["entity"] == "contact"
                        else None,
                    )
                    await session.flush()
                    custom_written = await _apply_custom_values(
                        session, normalized, plan["entity"], created.id, current_user.id, job.update_mode
                    )
                    _record_row(
                        session,
                        job,
                        idx,
                        raw_row,
                        normalized,
                        "added",
                        f"{custom_written} custom field(s)" if custom_written else None,
                        created,
                        plan["entity"],
                    )
                counters["added"] += 1
                # Register only after the savepoint released — a rolled-back
                # create must not stay findable by later rows.
                _register(created, plan["entity"], normalized)
            except Exception as exc:
                await _flag_row_rejected(idx, raw_row, normalized, exc, plan["entity"])

            if (job.rows_processed or 0) % _FLUSH_EVERY == 0:
                _persist_counters(job, counters)
                await session.commit()

        job.status = "completed"
    except Exception as exc:
        # Only non-row failures reach this (row-level problems are caught by
        # the per-row savepoints above). Every batch committed before it is
        # kept; the in-flight batch is rolled back and the counters are
        # recomputed from the rows that actually made it to disk.
        await session.rollback()
        logger.exception("Import job %s failed part-way", job_id)
        await session.refresh(job)
        stmt = (
            select(ImportRow.status, func.count(ImportRow.id))
            .where(ImportRow.import_job_id == job.id)
            .group_by(ImportRow.status)
        )
        by_status = {row[0]: row[1] for row in (await session.execute(stmt)).fetchall()}
        job.rows_added = by_status.get("added", 0)
        job.rows_updated = by_status.get("updated", 0)
        job.rows_unchanged = by_status.get("unchanged", 0)
        job.rows_duplicate = by_status.get("duplicate", 0)
        job.rows_skipped = by_status.get("skipped", 0)
        job.rows_invalid = by_status.get("invalid", 0)
        job.rows_processed = sum(by_status.values())
        job.status = "failed"
        job.finished_at = _utcnow()
        job.error_summary = (
            f"Import stopped after {job.rows_processed} of {job.rows_total} row(s): {exc} "
            "Rows committed before the failure were kept."
        )
        await session.commit()
        raise ImportError(f"Import stopped part-way — {job.rows_processed} row(s) kept: {exc}") from exc
    finally:
        job.finished_at = _utcnow()

    job.rows_added = counters["added"]
    job.rows_updated = counters["updated"]
    job.rows_unchanged = counters["unchanged"]
    job.rows_duplicate = counters["duplicate"]
    job.rows_skipped = counters["skipped"]
    job.rows_invalid = counters["invalid"]
    if counters["invalid"] or counters["skipped"]:
        job.error_summary = (
            f"{counters['invalid']} invalid row(s), {counters['skipped']} skipped row(s). "
            "Download the error report for details."
        )

    await record_activity(
        session,
        action="import_completed",
        user_id=current_user.id,
        entity_type="import_jobs",
        entity_id=job.id,
        description=f"Imported {job.filename}: +{counters['added']} added, ~{counters['updated']} updated",
        metadata={"strategy": job.strategy, "update_mode": job.update_mode, "counts": counters},
    )
    await session.commit()
    await session.refresh(job)

    return _job_summary(job)


@router.get("/import/progress/{job_id}")
async def import_progress(
    job_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    """Live counters for a job, plus a percentage when a total is known."""
    job = await _owned_job(session, job_id, current_user.id)
    stmt = (
        select(ImportRow.status, func.count(ImportRow.id))
        .where(ImportRow.import_job_id == job.id)
        .group_by(ImportRow.status)
    )
    by_status = {row[0]: row[1] for row in (await session.execute(stmt)).fetchall()}
    total = job.rows_total or 0
    processed = job.rows_processed or 0
    return {
        "job_id": job.id,
        "status": job.status,
        "rows_total": total,
        "rows_processed": processed,
        "percent": round((processed / total) * 100, 1) if total else 0.0,
        "by_status": by_status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_summary": job.error_summary,
    }


@router.get("/import/history")
async def import_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    total = (
        await session.execute(select(func.count(ImportJob.id)).where(ImportJob.created_by_id == current_user.id))
    ).scalar() or 0
    stmt = (
        select(ImportJob)
        .where(ImportJob.created_by_id == current_user.id)
        .order_by(ImportJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    jobs = list((await session.execute(stmt)).scalars().all())
    return {"jobs": [_job_summary(j) for j in jobs], "total": total, "page": page, "page_size": page_size}


@router.get("/import/{job_id}")
async def import_job_detail(
    job_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    job = await _owned_job(session, job_id, current_user.id)
    stmt = (
        select(ImportRow.status, func.count(ImportRow.id))
        .where(ImportRow.import_job_id == job.id)
        .group_by(ImportRow.status)
    )
    by_status = {row[0]: row[1] for row in (await session.execute(stmt)).fetchall()}
    return {**_job_summary(job), "by_status": by_status, "sheet_names": job.sheet_names or []}


# ---------------------------------------------------------------------------
# Error report
# ---------------------------------------------------------------------------


@router.get("/import/errors/{job_id}")
async def download_errors(
    job_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    job = await _owned_job(session, job_id, current_user.id)
    stmt = (
        select(ImportErrorRow)
        .where(ImportErrorRow.import_job_id == job.id)
        .order_by(ImportErrorRow.row_index, ImportErrorRow.id)
    )
    errors = list((await session.execute(stmt)).scalars().all())
    data = [
        {
            "row_index": e.row_index,
            "field": e.field or "",
            "raw_value": e.raw_value or "",
            "severity": e.severity,
            "message": e.message,
        }
        for e in errors
    ]
    return {"job_id": job.id, "count": len(data), "data": data, "csv": _to_csv(data)}


@router.get("/import/download/{job_id}")
async def download_import_report(
    job_id: int,
    extension: str = Query("csv", pattern="^(csv|xlsx)$"),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Full per-row report: action taken and the field-level diff."""
    job = await _owned_job(session, job_id, current_user.id)
    stmt = select(ImportRow).where(ImportRow.import_job_id == job.id).order_by(ImportRow.row_index)
    rows = list((await session.execute(stmt)).scalars().all())

    records = []
    for r in rows:
        preview = r.update_preview or {}
        records.append(
            {
                "row_index": r.row_index,
                "action": r.status,
                "entity": r.suggested_entity or "",
                "message": r.error_message or "",
                "changed_fields": ", ".join(sorted(preview.keys())),
                "changes": "; ".join(
                    f"{f}: {_fmt(v.get('from'))} -> {_fmt(v.get('to'))}" for f, v in sorted(preview.items())
                ),
                "input": "; ".join(f"{k}={_fmt(v)}" for k, v in sorted((r.normalized_row or {}).items())),
            }
        )

    stem = f"import_{job.id}_report_{_utcnow().strftime('%Y%m%d_%H%M%S')}"
    if extension == "xlsx":
        dest = settings.uploads_path / f"{stem}.xlsx"
        pd.DataFrame(records).to_excel(dest, index=False, engine="openpyxl")
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        dest = settings.uploads_path / f"{stem}.csv"
        dest.write_text(_to_csv(records), encoding="utf-8-sig")
        media = "text/csv"

    return FileResponse(path=dest, filename=dest.name, media_type=media)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


async def _plan_row(
    session: AsyncSession,
    normalized: dict[str, Any],
    strategy: str,
    update_mode: str,
) -> dict[str, Any]:
    """Decide what would happen to a row, without writing anything."""
    entity = "company" if _looks_like_company(normalized) else ("contact" if _looks_like_contact(normalized) else None)
    if entity is None:
        return {
            "action": "invalid",
            "entity": None,
            "reason": "Could not classify row as company or contact",
            "changes": {},
        }

    existing = (
        await _find_company(session, normalized) if entity == "company" else await _find_contact(session, normalized)
    )

    if existing is None:
        if strategy == "update":
            return {
                "action": "skipped",
                "entity": entity,
                "reason": f"No matching {entity}; strategy is 'update' so new records are not created",
                "changes": {},
            }
        return {"action": "added", "entity": entity, "reason": None, "changes": {}}

    if strategy in ("skip_duplicates", "add"):
        return {
            "action": "skipped",
            "entity": entity,
            "duplicate_of": existing.id,
            "reason": (f"Matches existing {entity} #{existing.id}; strategy is '{strategy}' so it was left untouched"),
            "changes": {},
        }

    changes = _field_changes(existing, normalized, update_mode, entity)
    custom_pending = await _custom_pending(session, normalized, entity, existing.id, update_mode)
    if not changes and not custom_pending:
        return {
            "action": "unchanged",
            "entity": entity,
            "target": existing,
            "reason": "All mapped fields already match",
            "changes": {},
        }
    if not changes:
        return {
            "action": "updated",
            "entity": entity,
            "target": existing,
            "reason": f"{custom_pending} custom field(s) to write",
            "changes": {},
        }
    return {"action": "updated", "entity": entity, "target": existing, "reason": None, "changes": changes}


def _field_changes(
    existing: Any, normalized: dict[str, Any], update_mode: str, entity: str
) -> dict[str, dict[str, Any]]:
    """Field-level diff honouring the update mode.

    ``fill_empty`` never overwrites a populated column, which makes an import
    safe to re-run and satisfies the "never overwrite silently" requirement by
    construction. ``overwrite`` records every replaced value.
    """
    allowed = set(_COMPANY_FIELDS if entity == "company" else _CONTACT_FIELDS)
    target_field = "name" if entity == "company" else "full_name"

    changes: dict[str, dict[str, Any]] = {}
    for field, incoming in normalized.items():
        if field not in allowed or field == target_field:
            continue
        if incoming is None or incoming == "" or incoming == []:
            continue
        current = getattr(existing, field, None)
        if current == incoming:
            continue
        blank = current is None or current == "" or current == []
        if not blank and update_mode == "fill_empty":
            continue
        changes[field] = {
            "field": field,
            "from": current,
            "to": incoming,
            "action": "fill" if blank else "overwrite",
        }
    return changes


async def _find_company(session: AsyncSession, normalized: dict[str, Any]) -> Company | None:
    name = (normalized.get("company_name") or "").strip()
    website = (normalized.get("website") or "").strip()
    domain = (normalized.get("domain") or "").strip()
    if not (name or website or domain):
        return None

    if domain:
        found = (
            await session.execute(
                select(Company).where(func.lower(Company.domain) == domain.lower().removeprefix("www.")).limit(1)
            )
        ).scalar_one_or_none()
        if found:
            return found
    if website:
        host = _domain_from_url(website)
        if host:
            found = (
                await session.execute(select(Company).where(func.lower(Company.domain) == host).limit(1))
            ).scalar_one_or_none()
            if found:
                return found
    if name:
        return (
            await session.execute(select(Company).where(func.lower(Company.name) == name.lower()).limit(1))
        ).scalar_one_or_none()
    return None


async def _find_contact(session: AsyncSession, normalized: dict[str, Any]) -> Contact | None:
    email = (normalized.get("email") or "").strip()
    if email:
        found = (
            await session.execute(select(Contact).where(func.lower(Contact.email) == email.lower()).limit(1))
        ).scalar_one_or_none()
        if found:
            return found

    full_name = _full_name_for(normalized)
    if not full_name:
        return None
    candidates = list(
        (await session.execute(select(Contact).where(func.lower(Contact.full_name) == full_name.lower()).limit(5)))
        .scalars()
        .all()
    )
    if not candidates:
        parts = full_name.split(None, 1)
        if len(parts) == 2:
            candidates = list(
                (
                    await session.execute(
                        select(Contact)
                        .where(
                            func.lower(Contact.first_name) == parts[0].lower(),
                            func.lower(Contact.last_name) == parts[1].lower(),
                        )
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
    company = (normalized.get("company_name") or "").strip().lower()
    phone = canonical_for_matching(normalized.get("phone")) or ""
    linkedin = (normalized.get("linkedin_url") or "").strip().lower()
    for cand in candidates:
        same_company = bool(company) and (cand.company_name or "").strip().lower() == company
        same_phone = bool(phone) and (canonical_for_matching(cand.phone) or "") == phone
        same_linkedin = bool(linkedin) and (cand.linkedin_url or "").strip().lower() == linkedin
        if same_company or same_phone or same_linkedin:
            return cand
    return None


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


async def _apply_create(
    session: AsyncSession,
    normalized: dict[str, Any],
    entity: str,
    user_id: int | None,
    company: Company | None = None,
):
    if entity == "company":
        company = Company(
            name=(normalized.get("company_name") or "Unknown Company")[:300],
            website=normalized.get("website"),
            domain=_clean_domain(normalized.get("domain")) or _domain_from_url(normalized.get("website")),
            linkedin_url=normalized.get("linkedin_url"),
            industry=normalized.get("industry"),
            sub_industry=normalized.get("sub_industry"),
            employee_count=_coerce_int(normalized.get("employee_count")),
            company_size=normalized.get("company_size"),
            country=normalized.get("country"),
            state=normalized.get("state"),
            city=normalized.get("city"),
            headquarters=normalized.get("headquarters"),
            founded_year=_coerce_int(normalized.get("founded_year")),
            technologies=_as_list(normalized.get("technologies")),
            funding_stage=normalized.get("funding_stage"),
            company_status=normalized.get("company_status"),
            source=normalized.get("source") or "import",
            notes=normalized.get("notes"),
            created_by_id=user_id,
        )
        company.data_quality_score = _company_quality(company)
        session.add(company)
        return company

    contact = Contact(
        first_name=normalized.get("first_name"),
        last_name=normalized.get("last_name"),
        full_name=_full_name_for(normalized),
        job_title=normalized.get("job_title"),
        department=normalized.get("department"),
        seniority=normalized.get("seniority"),
        email=normalized.get("email"),
        email_status=normalized.get("email_status"),
        phone=normalized.get("phone"),
        phone_status=normalized.get("phone_status"),
        linkedin_url=normalized.get("linkedin_url"),
        company_name=normalized.get("company_name"),
        city=normalized.get("city"),
        country=normalized.get("country"),
        skills=_as_list(normalized.get("skills")),
        employment_history=normalized.get("employment_history") or [],
        source=normalized.get("source") or "import",
        notes=normalized.get("notes"),
        created_by_id=user_id,
    )
    contact.data_quality_score = _contact_quality(contact)

    # Link the contact to an existing company or create one if the import
    # row names a company that does not yet exist in the base.
    if contact.company_name:
        if company is None:
            company = (
                await session.execute(
                    select(Company).where(func.lower(Company.name) == contact.company_name.strip().lower()).limit(1)
                )
            ).scalar_one_or_none()
            if not company:
                company = Company(
                    name=contact.company_name.strip()[:300],
                    source="import",
                    created_by_id=user_id,
                )
                company.data_quality_score = _company_quality(company)
                session.add(company)
                await session.flush()
        contact.company_id = company.id
        contact.company_name = company.name

    session.add(contact)
    return contact


# asyncpg rejects statements with more than 32,767 parameters; stay safely below.
_MAX_IN_PARAMS = 30_000


def _chunked(seq: list[Any], size: int = 400) -> Iterator[list[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _bulk_load_contacts(
    session: AsyncSession, plan_rows: list[tuple[Any, Any]]
) -> tuple[dict[str, Contact], dict[str, list[Contact]], dict[tuple[str, str], list[Contact]]]:
    """One pass of chunked lookups: contacts by email, full name, and first+last."""
    email_keys: set[str] = set()
    name_keys: set[str] = set()
    firsts: set[str] = set()
    lasts: set[str] = set()
    for _idx, (tag, payload) in plan_rows:
        if tag == "inv":
            continue  # invalid-row plan carries no identity
        normalized: dict[str, Any] = payload
        email = (normalized.get("email") or "").strip().lower()
        if email:
            email_keys.add(email)
        full_name = _full_name_for(normalized)
        if full_name:
            name_keys.add(full_name.lower())
            parts = full_name.split(None, 1)
            if len(parts) == 2:
                firsts.add(parts[0].lower())
                lasts.add(parts[1].lower())

    by_email: dict[str, Contact] = {}
    by_name: dict[str, list[Contact]] = {}
    by_fl: dict[tuple[str, str], list[Contact]] = {}
    for chunk in _chunked(sorted(email_keys), 400):
        for c in (
            await session.execute(select(Contact).where(func.lower(Contact.email).in_(chunk)))
        ).scalars():
            if c.email:
                by_email[c.email.strip().lower()] = c
    for chunk in _chunked(sorted(name_keys), 400):
        for c in (
            await session.execute(select(Contact).where(func.lower(Contact.full_name).in_(chunk)))
        ).scalars():
            by_name.setdefault((c.full_name or "").strip().lower(), []).append(c)
    if firsts and lasts and len(firsts) + len(lasts) <= _MAX_IN_PARAMS:
        for c in (
            await session.execute(
                select(Contact).where(
                    func.lower(Contact.first_name).in_(sorted(firsts)),
                    func.lower(Contact.last_name).in_(sorted(lasts)),
                )
            )
        ).scalars():
            by_fl.setdefault(
                ((c.first_name or "").strip().lower(), (c.last_name or "").strip().lower()), []
            ).append(c)
    return by_email, by_name, by_fl


async def _bulk_load_companies(
    session: AsyncSession, plan_rows: list[tuple[Any, Any]]
) -> tuple[dict[str, Company], dict[str, Company]]:
    domain_keys: set[str] = set()
    name_keys: set[str] = set()
    for _idx, (tag, payload) in plan_rows:
        if tag == "inv":
            continue  # invalid-row plan carries no identity
        normalized = payload
        domain = (normalized.get("domain") or "").strip().lower().removeprefix("www.")
        if domain:
            domain_keys.add(domain)
        host = _domain_from_url(normalized.get("website"))
        if host:
            domain_keys.add(host)
        name = (normalized.get("company_name") or "").strip().lower()
        if name:
            name_keys.add(name)

    by_domain: dict[str, Company] = {}
    by_name: dict[str, Company] = {}
    for chunk in _chunked(sorted(domain_keys), 400):
        for c in (
            await session.execute(select(Company).where(func.lower(Company.domain).in_(chunk)))
        ).scalars():
            if c.domain:
                by_domain[c.domain.strip().lower().removeprefix("www.")] = c
    for chunk in _chunked(sorted(name_keys), 400):
        for c in (
            await session.execute(select(Company).where(func.lower(Company.name).in_(chunk)))
        ).scalars():
            by_name[(c.name or "").strip().lower()] = c
    return by_domain, by_name


async def _bulk_load_custom_fields(session: AsyncSession) -> dict[tuple[str, str], CustomField]:
    fields = (await session.execute(select(CustomField))).scalars()
    return {(f.entity_type, f.key): f for f in fields}


async def _bulk_load_custom_values(
    session: AsyncSession, contact_ids: set[int], company_ids: set[int]
) -> dict[str, dict[int, set[int]]]:
    """entity -> entity_id -> set of custom_field_ids that already have a value."""
    out: dict[str, dict[int, set[int]]] = {"contact": {}, "company": {}}
    for entity, ids in (("contact", sorted(contact_ids)), ("company", sorted(company_ids))):
        for chunk in _chunked(ids):
            for eid, fid in (
                await session.execute(
                    select(CustomFieldValue.entity_id, CustomFieldValue.custom_field_id).where(
                        CustomFieldValue.entity_type == entity,
                        CustomFieldValue.entity_id.in_(chunk),
                    )
                )
            ).all():
                out[entity].setdefault(eid, set()).add(fid)
    return out


def _match_contact_locally(
    normalized: dict[str, Any],
    by_email: dict[str, Contact],
    by_name: dict[str, list[Contact]],
    by_fl: dict[tuple[str, str], list[Contact]],
) -> Contact | None:
    email = (normalized.get("email") or "").strip().lower()
    if email and email in by_email:
        return by_email[email]
    full_name = _full_name_for(normalized)
    if not full_name:
        return None
    candidates = list(by_name.get(full_name.lower(), []))
    if not candidates:
        parts = full_name.split(None, 1)
        if len(parts) == 2:
            candidates = list(by_fl.get((parts[0].lower(), parts[1].lower()), []))
    if not candidates:
        return None
    company = (normalized.get("company_name") or "").strip().lower()
    phone = canonical_for_matching(normalized.get("phone")) or ""
    linkedin = (normalized.get("linkedin_url") or "").strip().lower()
    for cand in candidates:
        same_company = bool(company) and (cand.company_name or "").strip().lower() == company
        same_phone = bool(phone) and (canonical_for_matching(cand.phone) or "") == phone
        same_linkedin = bool(linkedin) and (cand.linkedin_url or "").strip().lower() == linkedin
        if same_company or same_phone or same_linkedin:
            return cand
    return None


def _match_company_locally(
    normalized: dict[str, Any],
    by_domain: dict[str, Company],
    by_name: dict[str, Company],
) -> Company | None:
    domain = (normalized.get("domain") or "").strip().lower().removeprefix("www.")
    if domain and domain in by_domain:
        return by_domain[domain]
    host = _domain_from_url(normalized.get("website"))
    if host and host in by_domain:
        return by_domain[host]
    name = (normalized.get("company_name") or "").strip().lower()
    if name:
        return by_name.get(name)
    return None


def _plan_action_locally(
    existing: Company | Contact | None,
    entity: str,
    normalized: dict[str, Any],
    strategy: str,
    update_mode: str,
    custom_fields_map: dict[tuple[str, str], CustomField],
    custom_values_map: dict[str, dict[int, set[int]]],
) -> dict[str, Any]:
    """In-memory twin of ``_plan_row`` — same decisions, no per-row queries."""
    if existing is None:
        if strategy == "update":
            return {
                "action": "skipped",
                "entity": entity,
                "reason": f"No matching {entity}; strategy is 'update' so new records are not created",
                "changes": {},
            }
        return {"action": "added", "entity": entity, "reason": None, "changes": {}}

    if strategy in ("skip_duplicates", "add"):
        return {
            "action": "skipped",
            "entity": entity,
            "duplicate_of": existing.id,
            "reason": f"Matches existing {entity} #{existing.id}; strategy is '{strategy}' so it was left untouched",
            "changes": {},
        }

    changes = _field_changes(existing, normalized, update_mode, entity)
    custom_pending = 0
    for _target, (custom_entity, custom_name, _value) in _custom_targets(normalized).items():
        if custom_entity != entity:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", custom_name.strip().lower()).strip("_")[:100]
        if not key:
            continue
        field = custom_fields_map.get((entity, key))
        if field is None:
            custom_pending += 1
            continue
        if update_mode == "overwrite":
            custom_pending += 1
            continue
        if field.id not in custom_values_map.get(entity, {}).get(existing.id, set()):
            custom_pending += 1

    if not changes and not custom_pending:
        return {
            "action": "unchanged",
            "entity": entity,
            "target": existing,
            "reason": "All mapped fields already match",
            "changes": {},
        }
    if not changes:
        return {
            "action": "updated",
            "entity": entity,
            "target": existing,
            "reason": f"{custom_pending} custom field(s) to write",
            "changes": {},
        }
    return {"action": "updated", "entity": entity, "target": existing, "reason": None, "changes": changes}


def _flag_duplicate(session: AsyncSession, entity: str, existing_id: int, created: Any, plan: dict[str, Any]) -> None:
    session.add(
        DuplicateCandidate(
            entity_type=entity,
            record_id=existing_id,
            match_id=created.id,
            match_type=plan.get("match_type") or "imported",
            match_score=float(plan.get("score") or 0.8),
            status="open",
            notes=plan.get("reason"),
        )
    )


def _record_row(
    session: AsyncSession,
    job: ImportJob,
    idx: Any,
    raw_row: dict[str, Any],
    normalized: dict[str, Any],
    row_status: str,
    message: str | None,
    target: Any,
    entity: str | None,
    update_preview: dict[str, Any] | None = None,
) -> None:
    row = ImportRow(
        import_job_id=job.id,
        raw_row=raw_row,
        normalized_row=normalized,
        update_preview=update_preview or {},
        suggested_entity=entity,
        status=row_status,
        error_message=message,
        row_index=int(idx),
    )
    if target is not None and entity == "company":
        row.target_company_id = target.id
    elif target is not None and entity == "contact":
        row.target_contact_id = target.id
    session.add(row)


def _record_error(
    session: AsyncSession,
    job: ImportJob,
    idx: Any,
    field: str | None,
    raw_value: Any,
    message: str | None,
    severity: str,
) -> None:
    session.add(
        ImportErrorRow(
            import_job_id=job.id,
            row_index=int(idx),
            field=field,
            raw_value=(str(raw_value)[:500] if raw_value is not None else None),
            message=(message or "Unknown error")[:2000],
            severity=severity,
        )
    )


# ---------------------------------------------------------------------------
# File handling helpers
# ---------------------------------------------------------------------------


def _owned_job_sync(job: ImportJob | None, user_id: int) -> ImportJob:
    if job is None or job.created_by_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return job


async def _owned_job(session: AsyncSession, job_id: int, user_id: int) -> ImportJob:
    return _owned_job_sync(await session.get(ImportJob, job_id), user_id)


def _job_path(job: ImportJob) -> Path:
    if not job.file_path:
        raise BadRequestError("The uploaded file is no longer available")
    path = Path(job.file_path)
    try:
        path.resolve().relative_to(settings.uploads_path.resolve())
    except ValueError as exc:
        # relative_to raises ValueError when the path escapes the uploads root.
        raise BadRequestError("Invalid upload path") from exc
    if not path.exists():
        raise BadRequestError("The uploaded file is no longer available")
    return path


def _load_frame(job: ImportJob) -> pd.DataFrame:
    if not job.mapping:
        raise BadRequestError("Column mapping has not been set for this import")
    try:
        df = _read_table(_job_path(job), job, sheet=job.sheet_name)
    except BadRequestError:
        raise
    except Exception as exc:
        raise ImportError(f"Could not read file: {exc}") from exc
    df.columns = _unique_columns([str(c).strip() for c in df.columns])
    return df


def _sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() not in {".xlsx", ".xls", ".xlsm"}:
        return ["csv"]
    with pd.ExcelFile(path) as book:
        return [str(s) for s in book.sheet_names]


def _read_table(path: Path, job: ImportJob, sheet: str | None = None, nrows: int | None = None) -> pd.DataFrame:
    if _is_spreadsheet(job.filename, job.file_mime) or path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(path, sheet_name=sheet or 0, nrows=nrows)
    return _read_csv(path, nrows=nrows)


def _read_csv(path: Path, nrows: int | None = None) -> pd.DataFrame:
    last: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, on_bad_lines="skip", nrows=nrows)
        except UnicodeDecodeError as exc:
            last = exc
        except pd.errors.ParserError as exc:
            raise ImportError(f"Could not parse the CSV: {exc}") from exc
    raise ImportError(f"Could not decode the CSV with any supported encoding: {last}")


def _count_rows(path: Path, job: ImportJob, sheet: str | None = None) -> int:
    try:
        if _is_spreadsheet(job.filename, job.file_mime):
            import openpyxl

            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                ws = book[sheet] if sheet and sheet in book.sheetnames else book[book.sheetnames[0]]
                return max(0, (ws.max_row or 1) - 1)
            finally:
                book.close()
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except Exception:
        return 0


def _validate_signature(ext: str, content: bytes) -> None:
    """Reject files whose bytes do not match their claimed type."""
    if ext == ".xlsx" and not content.startswith(b"PK\x03\x04"):
        raise BadRequestError("File is not a valid .xlsx workbook")
    if ext == ".xls" and not content.startswith(b"\xd0\xcf\x11\xe0"):
        raise BadRequestError("File is not a valid .xls workbook")
    if ext == ".csv":
        sample = content[:4096]
        if b"\x00" in sample:
            raise BadRequestError("File looks binary, not a CSV")
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            sample.decode("cp1252", errors="replace")


def _is_spreadsheet(job_filename: str | None, mime: str | None) -> bool:
    name = (job_filename or "").lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return True
    return bool(mime and ("spreadsheet" in mime.lower() or "excel" in mime.lower()))


def _file_extension(filename: str) -> str:
    if not filename:
        return ""
    lower = filename.lower()
    for ext in (".xlsx", ".xlsm", ".xls", ".csv"):
        if lower.endswith(ext):
            return ".xlsx" if ext == ".xlsm" else ext
    return lower.rsplit(".", 1)[-1] if "." in lower else ""


def _unique_columns(columns: list[str]) -> list[str]:
    """pandas renames duplicate headers; make that explicit and stable."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for col in columns:
        base = col or "column"
        if base in seen:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            out.append(base)
    return out


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _coerce_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]


def _clean_domain(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if "://" in text:
        text = _domain_from_url(text) or ""
    return text.removeprefix("www.") or None


def _domain_from_url(value: Any) -> str | None:
    if not value:
        return None
    from urllib.parse import urlparse

    text = str(value).strip()
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = (parsed.netloc or parsed.path).split("/")[0].lower().removeprefix("www.")
    return host if "." in host else None


def _full_name_for(normalized: dict[str, Any]) -> str | None:
    if normalized.get("full_name"):
        return str(normalized["full_name"]).strip()
    first = (normalized.get("first_name") or "").strip()
    last = (normalized.get("last_name") or "").strip()
    combo = " ".join(part for part in (first, last) if part).strip()
    return combo or None


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for src, dst in mapping.items():
        if not dst:
            continue
        value = raw.get(src)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in {"", "nan", "none", "null", "n/a", "-"}:
                continue
        if dst == "phone":
            parsed = normalize_phone(value)
            # Keep the canonical display form; the country code survives
            # because it is never stripped, only separators are.
            value = parsed.display if parsed else value
        normalized[dst] = value
    return normalized


def _parse_custom_target(target: str) -> tuple[str, str] | None:
    """Split a ``custom:<entity>:<Field Name>`` mapping target.

    Returns ``(entity, name)`` or None when the target is a standard field.
    """
    if not target.startswith("custom:"):
        return None
    parts = target.split(":", 2)
    if len(parts) != 3 or parts[1] not in ("contact", "company") or not parts[2].strip():
        return None
    return parts[1], parts[2].strip()


def _custom_targets(normalized: dict[str, Any]) -> dict[str, tuple[str, str, Any]]:
    """Custom-field assignments in a normalized row, keyed by mapping target."""
    out: dict[str, tuple[str, str, Any]] = {}
    for target, value in normalized.items():
        parsed = _parse_custom_target(target)
        if parsed is None or value in (None, "", []):
            continue
        entity, name = parsed
        out[target] = (entity, name, value)
    return out


async def _custom_pending(
    session: AsyncSession, normalized: dict[str, Any], entity: str, target_id: int, update_mode: str
) -> int:
    """How many custom values in a row would actually change the target."""
    pending = 0
    for _target, (custom_entity, name, _value) in _custom_targets(normalized).items():
        if custom_entity != entity:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")[:100]
        if not key:
            continue
        field = (
            await session.execute(select(CustomField).where(CustomField.entity_type == entity, CustomField.key == key))
        ).scalar_one_or_none()
        if field is None:
            pending += 1
            continue
        if update_mode == "overwrite":
            pending += 1
            continue
        existing = (
            await session.execute(
                select(CustomFieldValue).where(
                    CustomFieldValue.entity_type == entity,
                    CustomFieldValue.entity_id == target_id,
                    CustomFieldValue.custom_field_id == field.id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            pending += 1
    return pending


async def _apply_custom_values(
    session: AsyncSession,
    normalized: dict[str, Any],
    entity: str,
    target_id: int,
    user_id: int | None,
    update_mode: str,
) -> int:
    """Write a row's custom-field values; returns how many were written.

    Missing definitions are created as plain text fields so any number of
    extra spreadsheet columns can ride along on an import. A definition that
    already exists keeps its type, and values are validated against it —
    invalid values are reported as row errors instead of failing the run.
    Definitions are matched to the record kind being written.
    """
    written = 0
    for _target, (custom_entity, name, value) in _custom_targets(normalized).items():
        if custom_entity != entity:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")[:100]
        if not key:
            continue
        field = (
            await session.execute(select(CustomField).where(CustomField.entity_type == entity, CustomField.key == key))
        ).scalar_one_or_none()
        if field is None:
            field = CustomField(
                entity_type=entity,
                name=name.strip()[:100],
                key=key,
                field_type="text",
                created_by_id=user_id,
            )
            session.add(field)
            await session.flush()
        existing = (
            await session.execute(
                select(CustomFieldValue).where(
                    CustomFieldValue.entity_type == entity,
                    CustomFieldValue.entity_id == target_id,
                    CustomFieldValue.custom_field_id == field.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None and update_mode == "fill_empty":
            continue
        clean: Any = value if isinstance(value, str) else str(value)
        if field.field_type == "number":
            try:
                clean = float(clean) if "." in clean else int(clean)
            except (TypeError, ValueError):
                continue
        elif field.field_type == "boolean":
            lowered = clean.strip().lower()
            if lowered in {"true", "yes", "1", "y"}:
                clean = True
            elif lowered in {"false", "no", "0", "n"}:
                clean = False
            else:
                continue
        if existing is not None:
            existing.value = clean
        else:
            session.add(
                CustomFieldValue(
                    entity_type=entity, entity_id=target_id, custom_field_id=field.id, value=clean
                )
            )
        written += 1
    return written


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Automatic column mapping from common spreadsheet header spellings."""
    synonyms = {
        "company_name": (
            "company",
            "company name",
            "company_name",
            "organisation",
            "organization",
            "employer",
            "account",
            "name",
        ),
        "website": ("website", "url", "web", "homepage", "site"),
        "domain": ("domain", "company domain", "website domain"),
        "linkedin_url": ("linkedin", "linkedin url", "linkedin_url", "linkedin profile"),
        "industry": ("industry", "sector", "vertical"),
        "sub_industry": ("sub industry", "sub_industry", "subsector"),
        "employee_count": ("employees", "employee count", "employee_count", "headcount", "size"),
        "company_size": ("company size", "company_size", "size band"),
        "country": ("country", "nation"),
        "state": ("state", "region", "province"),
        "city": ("city", "town", "location"),
        "headquarters": ("headquarters", "hq"),
        "founded_year": ("founded", "founded_year", "founded year"),
        "technologies": ("technologies", "tech stack", "stack", "technology"),
        "funding_stage": ("funding", "funding stage", "funding_stage"),
        "company_status": ("status", "company status"),
        "source": ("source", "origin", "list source"),
        "notes": ("notes", "note", "comment", "comments", "remark"),
        "full_name": ("full name", "full_name", "name", "contact", "contact name", "person"),
        "first_name": ("first name", "first_name", "given name", "firstname"),
        "last_name": ("last name", "last_name", "surname", "family name", "lastname"),
        "job_title": ("title", "job title", "job_title", "designation", "role", "position"),
        "department": ("department", "function", "team"),
        "seniority": ("seniority", "level", "grade"),
        "email": ("email", "e-mail", "email address", "work email", "business email"),
        "email_status": ("email status", "email_status", "email verification"),
        "phone": ("phone", "mobile", "telephone", "cell", "phone number", "direct dial"),
        "phone_status": ("phone status", "phone_status"),
        "skills": ("skills", "expertise"),
        "employment_history": ("employment history", "experience", "work history"),
    }
    lookup: dict[str, str] = {}
    for field, variants in synonyms.items():
        for variant in variants:
            lookup.setdefault(variant.replace(" ", "").replace("_", ""), field)

    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    for col in columns:
        key = col.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        field = lookup.get(key)
        if field and field not in claimed:
            mapping[col] = field
            claimed.add(field)
    return mapping


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def _company_quality(data: Any) -> int:
    def get(field: str) -> Any:
        return getattr(data, field, None) if not isinstance(data, dict) else data.get(field)

    score = 0
    if get("name") or get("company_name"):
        score += 10
    if get("website"):
        score += 10
    if get("domain"):
        score += 5
    if get("linkedin_url"):
        score += 10
    if get("industry"):
        score += 5
    if get("city"):
        score += 5
    if get("country"):
        score += 5
    if get("employee_count") is not None:
        score += 5
    if get("founded_year") is not None:
        score += 5
    if get("technologies"):
        score += 5
    if isinstance(data, Company) and data.contacts:
        score += min(15, len(data.contacts) * 3)
    return min(100, score)


def _contact_quality(data: Any) -> int:
    def get(field: str) -> Any:
        return getattr(data, field, None) if not isinstance(data, dict) else data.get(field)

    score = 0
    if get("full_name") or get("first_name") or get("last_name"):
        score += 10
    if get("email"):
        score += 25
    if get("phone"):
        score += 20
    if get("linkedin_url"):
        score += 20
    if get("company_id") or get("company_name"):
        score += 15
    if get("job_title"):
        score += 10
    if isinstance(data, Contact) and data.last_verified:
        score += 10
    return min(100, score)


def _looks_like_company(normalized: dict[str, Any]) -> bool:
    """Classify a row as a company, unless it carries a contact identity.

    Contact identity wins, always. A spreadsheet column such as
    "Company Website" next to "Full Name"/"Email" describes the person's
    employer, not the row's subject, so the row is imported as a contact and
    the company is referenced through ``company_name`` (and linked to an
    existing company of that name - see ``_apply_create``).

    Classifying such a row as a company silently discarded every contact field
    in it, which is why this decision is made before looking at website, domain
    or company_name.
    """
    if _looks_like_contact(normalized):
        return False
    return bool(normalized.get("website") or normalized.get("domain") or normalized.get("company_name"))


def _looks_like_contact(normalized: dict[str, Any]) -> bool:
    return bool(
        normalized.get("full_name")
        or normalized.get("first_name")
        or normalized.get("last_name")
        or normalized.get("email")
        or normalized.get("phone")
        or normalized.get("job_title")
    )


def _to_csv(data: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    if not data:
        return ""
    keys: list[str] = []
    for row in data:
        for key in row:
            if key not in keys:
                keys.append(key)
    writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def _job_summary(job: ImportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "filename": job.filename,
        "file_size_bytes": job.file_size_bytes,
        "status": job.status,
        "strategy": job.strategy,
        "update_mode": job.update_mode,
        "sheet_name": job.sheet_name,
        "rows_total": job.rows_total,
        "rows_processed": job.rows_processed,
        "rows_added": job.rows_added,
        "rows_updated": job.rows_updated,
        "rows_unchanged": job.rows_unchanged,
        "rows_duplicate": job.rows_duplicate,
        "rows_invalid": job.rows_invalid,
        "rows_skipped": job.rows_skipped,
        "error_summary": job.error_summary,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
