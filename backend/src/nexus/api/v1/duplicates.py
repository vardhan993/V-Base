from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity, record_audit, snapshot
from nexus.core.db import get_session
from nexus.database import AuditLog, Company, Contact, DuplicateCandidate, ImportRow

router = APIRouter(tags=["duplicates"])

#: Similarity threshold for the trigram scan. 0.6 catches "Acme Inc" vs
#: "Acme, Inc." without flooding the queue with unrelated names.
_NAME_SIMILARITY = 0.6
_MAX_CANDIDATES_PER_ROW = 5

#: Fields shown side by side on the merge screen.
_COMPANY_COMPARE_FIELDS = (
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
_CONTACT_COMPARE_FIELDS = (
    "full_name",
    "first_name",
    "last_name",
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
    "source",
    "notes",
)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@router.get("/duplicates")
async def list_duplicates(
    status_filter: str = Query("open", pattern="^(open|resolved|ignored)$", alias="status"),
    entity_type: str | None = Query(None, pattern="^(company|contact)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    filters = [DuplicateCandidate.status == status_filter]
    if entity_type:
        filters.append(DuplicateCandidate.entity_type == entity_type)

    total = (await session.execute(select(func.count(DuplicateCandidate.id)).where(*filters))).scalar() or 0
    stmt = (
        select(DuplicateCandidate)
        .where(*filters)
        .order_by(DuplicateCandidate.match_score.desc(), DuplicateCandidate.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    candidates = list((await session.execute(stmt)).scalars().all())

    items = []
    for c in candidates:
        record = match = None
        if c.entity_type == "contact":
            record = await session.get(Contact, c.record_id)
            match = await session.get(Contact, c.match_id)
        elif c.entity_type == "company":
            record = await session.get(Company, c.record_id)
            match = await session.get(Company, c.match_id)
        items.append(
            {
                "id": c.id,
                "entity_type": c.entity_type,
                "record_id": c.record_id,
                "match_id": c.match_id,
                "match_type": c.match_type,
                "match_score": c.match_score,
                "status": c.status,
                "notes": c.notes,
                "record": _summary(record),
                "match": _summary(match),
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/duplicates/{candidate_id}/compare")
async def compare_duplicates(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Field-by-field side-by-side view with conflict highlighting."""
    candidate = await session.get(DuplicateCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found")

    model = Contact if candidate.entity_type == "contact" else Company
    fields = _CONTACT_COMPARE_FIELDS if candidate.entity_type == "contact" else _COMPANY_COMPARE_FIELDS
    record = await session.get(model, candidate.record_id)
    match = await session.get(model, candidate.match_id)

    rows = []
    for field in fields:
        left = getattr(record, field, None) if record else None
        right = getattr(match, field, None) if match else None
        rows.append(
            {
                "field": field,
                "record_value": _plain(left),
                "match_value": _plain(right),
                "conflict": _plain(left) != _plain(right) and bool(left) and bool(right),
                "suggestion": _suggest(left, right),
            }
        )

    return {
        "id": candidate.id,
        "entity_type": candidate.entity_type,
        "match_type": candidate.match_type,
        "match_score": candidate.match_score,
        "status": candidate.status,
        "record": {"id": candidate.record_id, "fields": rows},
        "match": {"id": candidate.match_id, "summary": _summary(match)},
        "summary": _summary(record),
        "history": await _candidate_history(session, candidate),
    }


@router.post("/duplicates/scan", status_code=status.HTTP_200_OK)
async def scan_duplicates(
    entity_type: str = Query("both", pattern="^(both|company|contact)$"),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Find duplicate candidates using PostgreSQL trigram similarity.

    Company pairs are discovered through an index-assisted lateral join on the
    ``gin_trgm_ops`` index over ``companies.name``, plus an exact domain match.
    Contacts are matched on case-insensitive email, or on near-identical names
    that share a company or phone number.
    """
    created = 0
    matched_companies = 0
    matched_contacts = 0

    if entity_type in ("both", "company"):
        rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT a.id AS left_id, b.id AS right_id,
                           similarity(lower(a.name), lower(b.name)) AS score,
                           (a.domain IS NOT NULL AND lower(a.domain) = lower(b.domain)) AS same_domain
                    FROM companies a
                    JOIN LATERAL (
                        SELECT id, name, domain
                        FROM companies b
                        WHERE b.id <> a.id
                          AND b.is_archived = false
                          AND (lower(b.name) % lower(a.name)
                               OR (a.domain IS NOT NULL AND lower(b.domain) = lower(a.domain)))
                        ORDER BY similarity(lower(a.name), lower(b.name)) DESC
                        LIMIT :per_row
                    ) b ON true
                    WHERE a.is_archived = false
                    ORDER BY score DESC
                    LIMIT :limit
                    """
                    ),
                    {"per_row": _MAX_CANDIDATES_PER_ROW, "limit": limit},
                )
            )
            .mappings()
            .all()
        )

        for row in rows:
            left, right = sorted((int(row["left_id"]), int(row["right_id"])))
            if await _candidate_exists(session, "company", left, right):
                continue
            score = 1.0 if row["same_domain"] else float(row["score"] or 0.0)
            if score < _NAME_SIMILARITY:
                continue
            session.add(
                DuplicateCandidate(
                    entity_type="company",
                    record_id=left,
                    match_id=right,
                    match_type="domain" if row["same_domain"] else "name",
                    match_score=round(min(1.0, score), 3),
                    status="open",
                    notes=f"Detected by automatic scan (similarity {score:.2f})",
                )
            )
            matched_companies += 1
            created += 1

    if entity_type in ("both", "contact"):
        # Exact email collisions: the strongest duplicate signal for people.
        email_rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT a.id AS left_id, b.id AS right_id
                    FROM contacts a
                    JOIN contacts b
                      ON b.id > a.id
                     AND a.email IS NOT NULL AND b.email IS NOT NULL
                     AND lower(a.email) = lower(b.email)
                    WHERE a.is_archived = false AND b.is_archived = false
                    LIMIT :limit
                    """
                    ),
                    {"limit": limit},
                )
            )
            .mappings()
            .all()
        )

        for row in email_rows:
            if await _candidate_exists(session, "contact", int(row["left_id"]), int(row["right_id"])):
                continue
            session.add(
                DuplicateCandidate(
                    entity_type="contact",
                    record_id=int(row["left_id"]),
                    match_id=int(row["right_id"]),
                    match_type="email",
                    match_score=1.0,
                    status="open",
                    notes="Identical email address",
                )
            )
            matched_contacts += 1
            created += 1

        # Near-identical names that share a company or phone number.
        name_rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT a.id AS left_id, b.id AS right_id,
                           similarity(lower(a.full_name), lower(b.full_name)) AS score
                    FROM contacts a
                    JOIN LATERAL (
                        SELECT id, full_name
                        FROM contacts b
                        WHERE b.id <> a.id
                          AND b.is_archived = false
                          AND b.full_name IS NOT NULL
                          AND lower(b.full_name) % lower(a.full_name)
                          AND (lower(coalesce(b.company_name,'')) = lower(coalesce(a.company_name,''))
                               OR (b.phone IS NOT NULL AND b.phone = a.phone))
                        ORDER BY similarity(lower(a.full_name), lower(b.full_name)) DESC
                        LIMIT :per_row
                    ) b ON true
                    WHERE a.is_archived = false AND a.full_name IS NOT NULL
                    ORDER BY score DESC
                    LIMIT :limit
                    """
                    ),
                    {"per_row": _MAX_CANDIDATES_PER_ROW, "limit": limit},
                )
            )
            .mappings()
            .all()
        )

        for row in name_rows:
            left, right = sorted((int(row["left_id"]), int(row["right_id"])))
            if await _candidate_exists(session, "contact", left, right):
                continue
            score = float(row["score"] or 0.0)
            if score < 0.8:
                continue
            session.add(
                DuplicateCandidate(
                    entity_type="contact",
                    record_id=left,
                    match_id=right,
                    match_type="name+company",
                    match_score=round(min(1.0, score), 3),
                    status="open",
                    notes=f"Same name and company/phone (similarity {score:.2f})",
                )
            )
            matched_contacts += 1
            created += 1

    if created:
        await record_activity(
            session,
            action="duplicate_scan",
            user_id=current_user.id,
            entity_type="duplicates",
            description=f"Duplicate scan found {created} new candidate(s)",
            metadata={"companies": matched_companies, "contacts": matched_contacts},
        )
    await session.commit()
    return {
        "created": created,
        "companies": matched_companies,
        "contacts": matched_contacts,
        "threshold": _NAME_SIMILARITY,
    }


@router.post("/duplicates/{candidate_id}/merge", status_code=status.HTTP_200_OK)
async def merge_duplicates(
    candidate_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Merge two records, keeping one and folding the other's values in.

    Fields are only taken from the discarded record when the surviving record
    has nothing there, so an existing value is never silently replaced.
    """
    candidate = await session.get(DuplicateCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found")
    if candidate.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Candidate is already resolved")

    keep_id = body.get("keep_record_id")
    if keep_id not in (candidate.record_id, candidate.match_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_record_id must be one of the two matched records",
        )

    model = Contact if candidate.entity_type == "contact" else Company
    fields = _CONTACT_COMPARE_FIELDS if candidate.entity_type == "contact" else _COMPANY_COMPARE_FIELDS

    record = await session.get(model, candidate.record_id)
    match = await session.get(model, candidate.match_id)
    keep = record if record and record.id == keep_id else match
    other = match if record and record.id == keep_id else record

    if keep is None or other is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One of the matched records no longer exists; refresh the duplicate list",
        )

    before = snapshot(keep, list(fields))
    merged_fields: list[str] = []
    for attr in fields:
        other_value = getattr(other, attr, None)
        keep_value = getattr(keep, attr, None)
        if other_value and not keep_value:
            setattr(keep, attr, other_value)
            merged_fields.append(attr)

    if candidate.entity_type == "contact":
        if other.company_id and not keep.company_id:
            keep.company_id = other.company_id
        await _move_contact_relations(session, other.id, keep.id)
        await _detach_import_rows(session, "target_contact_id", other.id)
    else:
        if other.created_by_id and not keep.created_by_id:
            keep.created_by_id = other.created_by_id
        await _move_company_relations(session, other.id, keep.id)
        await _detach_import_rows(session, "target_company_id", other.id)

    keep.data_quality_score = max(keep.data_quality_score or 0, other.data_quality_score or 0)

    discarded_id = other.id
    await session.delete(other)

    candidate.status = "resolved"
    candidate.resolved_by_id = current_user.id
    candidate.resolved_at = _utcnow()
    candidate.notes = ((candidate.notes or "") + f" Merged #{discarded_id} into #{keep.id}.").strip()

    await record_activity(
        session,
        action="duplicate_merged",
        user_id=current_user.id,
        entity_type=candidate.entity_type,
        entity_id=keep.id,
        description=f"Merged {candidate.entity_type} #{discarded_id} into #{keep.id}",
        metadata={"candidate_id": candidate.id, "merged_fields": merged_fields},
    )
    await record_audit(
        session,
        action="merge",
        entity_type=candidate.entity_type,
        entity_id=keep.id,
        user_id=current_user.id,
        before=before,
        after=snapshot(keep, list(fields)),
        reason=f"Duplicate merge (candidate #{candidate.id}); discarded #{discarded_id}",
    )
    await session.commit()
    return {
        "status": "merged",
        "keep_record_id": keep.id,
        "discarded_record_id": discarded_id,
        "merged_fields": merged_fields,
    }


@router.post("/duplicates/{candidate_id}/keep-both", status_code=status.HTTP_200_OK)
async def keep_both(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    candidate = await session.get(DuplicateCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found")
    candidate.status = "resolved"
    candidate.resolved_by_id = current_user.id
    candidate.resolved_at = _utcnow()
    candidate.notes = ((candidate.notes or "") + " Reviewed: both records are distinct.").strip()
    await record_activity(
        session,
        action="duplicate_reviewed",
        user_id=current_user.id,
        entity_type=candidate.entity_type,
        entity_id=candidate.record_id,
        description="Reviewed duplicate pair and kept both records",
        metadata={"candidate_id": candidate.id},
    )
    await session.commit()
    return {"status": "kept_both"}


@router.post("/duplicates/{candidate_id}/ignore", status_code=status.HTTP_200_OK)
async def ignore_duplicate(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    candidate = await session.get(DuplicateCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found")
    candidate.status = "ignored"
    candidate.resolved_by_id = current_user.id
    candidate.resolved_at = _utcnow()
    await record_activity(
        session,
        action="duplicate_dismissed",
        user_id=current_user.id,
        entity_type=candidate.entity_type,
        entity_id=candidate.record_id,
        description="Dismissed a duplicate suggestion",
        metadata={"candidate_id": candidate.id},
    )
    await session.commit()
    return {"status": "ignored"}


@router.post("/duplicates/{candidate_id}/reopen", status_code=status.HTTP_200_OK)
async def reopen_duplicate(
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    candidate = await session.get(DuplicateCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found")
    candidate.status = "open"
    candidate.resolved_by_id = None
    candidate.resolved_at = None
    await session.commit()
    return {"status": "reopened"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary(record) -> dict[str, Any] | None:
    if record is None:
        return None
    if isinstance(record, Contact):
        return {
            "id": record.id,
            "name": record.display_name,
            "email": record.email,
            "phone": record.phone,
            "company_name": record.company_name,
            "job_title": record.job_title,
            "data_quality_score": record.data_quality_score,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
    if isinstance(record, Company):
        return {
            "id": record.id,
            "name": record.name,
            "domain": record.domain,
            "website": record.website,
            "linkedin_url": record.linkedin_url,
            "industry": record.industry,
            "city": record.city,
            "contact_count": len(record.contacts or []),
            "data_quality_score": record.data_quality_score,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
    return {"id": getattr(record, "id", None)}


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else None
    return value


def _suggest(left: Any, right: Any) -> Any:
    """Which side to keep for a field: prefer the non-empty, longer value."""
    if left and not right:
        return left
    if right and not left:
        return right
    if left and right and str(left) != str(right):
        return left if len(str(left)) >= len(str(right)) else right
    return None


async def _candidate_exists(session: AsyncSession, entity_type: str, record_id: int, match_id: int) -> bool:
    stmt = (
        select(DuplicateCandidate.id)
        .where(
            DuplicateCandidate.entity_type == entity_type,
            DuplicateCandidate.record_id == record_id,
            DuplicateCandidate.match_id == match_id,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _candidate_history(session: AsyncSession, candidate: DuplicateCandidate) -> list[dict[str, Any]]:
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.entity_type == candidate.entity_type,
            AuditLog.entity_id.in_([candidate.record_id, candidate.match_id]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(25)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_id": row.entity_id,
            "reason": row.reason,
            "user_id": row.user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _move_contact_relations(session: AsyncSession, from_id: int, to_id: int) -> None:
    """Re-point child rows at the surviving contact before the duplicate goes."""
    from nexus.database import ContactTag, ListContact

    for model in (ContactTag, ListContact):
        rows = list((await session.execute(select(model).where(model.contact_id == from_id))).scalars().all())
        for row in rows:
            exists = (
                (
                    await session.execute(select(model.id).where(model.contact_id == to_id, model.tag_id == row.tag_id))
                ).scalar_one_or_none()
                if model is ContactTag
                else (
                    await session.execute(
                        select(model.id).where(model.contact_id == to_id, model.list_id == row.list_id)
                    )
                ).scalar_one_or_none()
            )
            if exists:
                await session.delete(row)
            else:
                row.contact_id = to_id


async def _move_company_relations(session: AsyncSession, from_id: int, to_id: int) -> None:
    from nexus.database import CompanyTag, Contact, ListCompany

    rows = list((await session.execute(select(CompanyTag).where(CompanyTag.company_id == from_id))).scalars().all())
    for row in rows:
        exists = (
            await session.execute(
                select(CompanyTag.id).where(CompanyTag.company_id == to_id, CompanyTag.tag_id == row.tag_id)
            )
        ).scalar_one_or_none()
        if exists:
            await session.delete(row)
        else:
            row.company_id = to_id

    rows = list((await session.execute(select(ListCompany).where(ListCompany.company_id == from_id))).scalars().all())
    for row in rows:
        exists = (
            await session.execute(
                select(ListCompany.id).where(ListCompany.company_id == to_id, ListCompany.list_id == row.list_id)
            )
        ).scalar_one_or_none()
        if exists:
            await session.delete(row)
        else:
            row.company_id = to_id

    # Contacts that pointed at the duplicate now point at the survivor.
    await session.execute(update(Contact).where(Contact.company_id == from_id).values(company_id=to_id))


async def _detach_import_rows(session: AsyncSession, column: str, record_id: int) -> None:
    """Clear import-row references so the merged-away record can be deleted."""
    col = getattr(ImportRow, column)
    rows = list((await session.execute(select(ImportRow).where(col == record_id))).scalars().all())
    for row in rows:
        setattr(row, column, None)
