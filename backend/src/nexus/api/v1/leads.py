"""Leads: the qualification funnel ahead of contacts and companies.

A lead is a prospect that may never qualify, so it lives in its own table and
is only promoted to a durable Contact (/ Company) by the convert endpoint.
That endpoint either matches an existing record or creates one, and it refuses
to create a second record when a match already exists — a conversion can never
silently duplicate a person or an organisation.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity, record_audit, snapshot
from nexus.core.counts import attach_contact_counts_for_company
from nexus.core.db import get_session
from nexus.core.lead_scoring import (
    SETTINGS_KEY,
    build_config,
    default_config_payload,
    score_breakdown_or_empty,
    score_lead,
    split_scores,
    summarise,
)
from nexus.core.quality import company_quality, contact_quality
from nexus.database import (
    CRM_STAGES,
    ActivityLog,
    Company,
    Contact,
    Lead,
    LeadTag,
    SettingsRow,
    Tag,
)
from nexus.schemas.company import CompanyResponse
from nexus.schemas.contact import ContactResponse
from nexus.schemas.lead import (
    LeadConvertRequest,
    LeadConvertResponse,
    LeadCreate,
    LeadExportRow,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)

router = APIRouter(tags=["leads"])

#: Columns captured in audit before/after payloads.
_AUDIT_FIELDS = [
    "full_name",
    "first_name",
    "last_name",
    "job_title",
    "email",
    "phone",
    "linkedin_url",
    "company_name",
    "company_domain",
    "industry",
    "employee_count",
    "city",
    "state",
    "country",
    "lead_source",
    "campaign",
    "lifecycle_stage",
    "lead_status",
    "priority",
    "lead_score",
    "owner_id",
    "company_id",
    "next_follow_up_at",
    "consent_status",
    "do_not_contact",
    "converted_contact_id",
    "converted_company_id",
    "converted_at",
    "is_archived",
]

#: Changing any of these invalidates the score, so it is recomputed.
_SCORED_FIELDS = frozenset(
    {
        "email",
        "phone",
        "linkedin_url",
        "job_title",
        "seniority",
        "company_name",
        "company_id",
        "company_domain",
        "industry",
        "employee_count",
        "country",
        "city",
        "next_follow_up_at",
        "consent_status",
    }
)

_RECENT_ACTIVITY_DAYS = 30


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


async def _load_scoring_config(session: AsyncSession):
    """Active scoring configuration, falling back to the defaults."""
    result = await session.execute(select(SettingsRow).where(SettingsRow.key == SETTINGS_KEY))
    settings_row = result.scalar_one_or_none()
    return build_config(settings_row.value if settings_row else None)


async def _activity_counts(session: AsyncSession, lead_id: int) -> tuple[int, int]:
    """(total, recent) activity rows for a lead. Real rows only."""
    total = (
        await session.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.entity_type == "leads", ActivityLog.entity_id == lead_id)
        )
    ).scalar() or 0
    since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=_RECENT_ACTIVITY_DAYS)
    recent = (
        await session.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.entity_type == "leads",
                ActivityLog.entity_id == lead_id,
                ActivityLog.created_at >= since,
            )
        )
    ).scalar() or 0
    return int(total), int(recent)


async def _apply_score(session: AsyncSession, lead: Lead, config=None, *, commit: bool = False) -> None:
    """Recompute and store the lead's score and explainable breakdown."""
    if config is None:
        config = await _load_scoring_config(session)
    total, recent = await _activity_counts(session, lead.id)
    result = score_lead(lead, config=config, activity_count=total, recent_activity_count=recent)
    lead.lead_score = result.total_score
    lead.score_breakdown = result.breakdown
    lead.score_updated_at = datetime.datetime.now(datetime.UTC)
    if commit:
        await session.commit()
        await session.refresh(lead)


def _serialise(lead: Lead) -> LeadResponse:
    """Response model plus the derived split and one-line explanation."""
    resp = LeadResponse.model_validate(lead)
    resp.display_name = lead.display_name
    breakdown = score_breakdown_or_empty(lead.score_breakdown)
    resp.fit_score, resp.engagement_score = split_scores(breakdown)
    resp.score_summary = summarise(breakdown)
    return resp


def _lead_quality(lead: Lead | LeadCreate) -> int:
    """Completeness score, in the same spirit as contacts and companies."""
    score = 0
    if lead.full_name or lead.first_name or lead.last_name:
        score += 10
    if lead.email:
        score += 25
    if lead.phone:
        score += 20
    if lead.linkedin_url:
        score += 15
    if lead.company_name or getattr(lead, "company_id", None):
        score += 15
    if lead.job_title:
        score += 10
    if getattr(lead, "industry", None):
        score += 5
    return min(100, score)


async def _get_or_create_tag(session: AsyncSession, name: str) -> Tag:
    result = await session.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name, kind="lead")
        session.add(tag)
        await session.flush()
    return tag


async def _match_company(session: AsyncSession, name: str | None, domain: str | None) -> Company | None:
    """Find a company by exact name (case-insensitive) or domain."""
    conditions = []
    if name:
        conditions.append(func.lower(Company.name) == name.strip().lower())
    if domain:
        conditions.append(func.lower(Company.domain) == domain.strip().lower())
    if not conditions:
        return None
    result = await session.execute(select(Company).where(or_(*conditions)).limit(1))
    return result.scalars().first()


async def _match_contact(session: AsyncSession, email: str | None) -> Contact | None:
    if not email:
        return None
    result = await session.execute(
        select(Contact).where(func.lower(Contact.email) == email.strip().lower()).limit(1)
    )
    return result.scalars().first()


def _lead_sort_column(sort: str):
    mapping = {
        "updated_at": Lead.updated_at,
        "created_at": Lead.created_at,
        "full_name": Lead.full_name,
        "company_name": Lead.company_name,
        "lead_score": Lead.lead_score,
        "next_follow_up_at": Lead.next_follow_up_at,
        "lifecycle_stage": Lead.lifecycle_stage,
        "lead_status": Lead.lead_status,
        "priority": Lead.priority,
        "email": Lead.email,
    }
    return mapping.get(sort, Lead.updated_at)


# ---------------------------------------------------------------------------
# Scoring rules (registered before /leads/{lead_id})
# ---------------------------------------------------------------------------


@router.get("/leads/scoring-rules")
async def get_scoring_rules(
    session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    """The active lead-scoring configuration, defaults filled in."""
    result = await session.execute(select(SettingsRow).where(SettingsRow.key == SETTINGS_KEY))
    row = result.scalar_one_or_none()
    payload = default_config_payload()
    if row and isinstance(row.value, dict):
        for key in ("weights", "target_industries", "target_countries", "size_band"):
            if row.value.get(key) is not None:
                payload[key] = row.value[key]
    payload["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    return payload


@router.put("/leads/scoring-rules")
async def update_scoring_rules(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Replace the scoring configuration. Administrators only."""
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can change lead scoring rules",
        )
    allowed = {"weights", "target_industries", "target_countries", "size_band"}
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scoring setting(s): {', '.join(sorted(unknown))}",
        )
    # Validate by building a config from the payload; a malformed value is a
    # 400 rather than a silently ignored setting.
    config_payload = {key: body[key] for key in allowed if key in body}
    if "weights" in config_payload and not isinstance(config_payload["weights"], dict):
        raise HTTPException(status_code=400, detail="weights must be an object of rule key -> number")
    if "weights" in config_payload:
        for key, value in config_payload["weights"].items():
            from nexus.core.lead_scoring import DEFAULT_WEIGHTS

            if key not in DEFAULT_WEIGHTS:
                raise HTTPException(status_code=400, detail=f"Unknown scoring rule: {key}")
            if not isinstance(value, (int, float)) or value < 0:
                raise HTTPException(status_code=400, detail=f"weights.{key} must be a non-negative number")
    build_config(config_payload)

    result = await session.execute(select(SettingsRow).where(SettingsRow.key == SETTINGS_KEY))
    row = result.scalar_one_or_none()
    if row is None:
        row = SettingsRow(key=SETTINGS_KEY, value=config_payload, updated_by_id=current_user.id)
        session.add(row)
    else:
        merged = dict(row.value or {})
        merged.update(config_payload)
        row.value = merged
        row.updated_by_id = current_user.id
    await record_audit(
        session,
        action="update",
        entity_type="settings",
        entity_id=row.id or 0,
        user_id=current_user.id,
        after={"key": SETTINGS_KEY, "value": config_payload},
    )
    await session.commit()
    return await get_scoring_rules(session=session, current_user=current_user)


# ---------------------------------------------------------------------------
# List / export
# ---------------------------------------------------------------------------


@router.get("/leads", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=500),
    name: str = Query("", max_length=300),
    email: str = Query("", max_length=254),
    phone: str = Query("", max_length=50),
    company_name: str = Query("", max_length=300),
    industry: str | None = Query(None, max_length=200),
    city: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=100),
    lead_source: str | None = Query(None, max_length=200),
    campaign: str | None = Query(None, max_length=200),
    lifecycle_stage: str | None = Query(None, max_length=50),
    lead_status: str | None = Query(None, max_length=50),
    priority: str | None = Query(None, max_length=20),
    owner_id: int | None = Query(None),
    company_id: int | None = Query(None),
    tags: str = Query("", max_length=500),
    min_score: int | None = Query(None, ge=0, le=100),
    max_score: int | None = Query(None, ge=0, le=100),
    follow_up_before: datetime.datetime | None = Query(None),
    overdue_follow_up: bool | None = Query(None),
    has_email: bool | None = Query(None),
    has_phone: bool | None = Query(None),
    converted: bool | None = Query(None),
    do_not_contact: bool | None = Query(None),
    sort: str = Query("updated_at"),
    order: str = Query("desc"),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Lead).where(
        Lead.is_archived.is_(False) if archived is None else Lead.is_archived == archived
    )

    if q:
        base = base.where(Lead.search_filter(q))
    if name:
        base = base.where(
            (Lead.full_name.ilike(f"%{name}%"))
            | (Lead.first_name.ilike(f"%{name}%"))
            | (Lead.last_name.ilike(f"%{name}%"))
        )
    if email:
        base = base.where(Lead.email.ilike(f"%{email}%"))
    if phone:
        base = base.where(Lead.phone.ilike(f"%{phone}%"))
    if company_name:
        base = base.where(Lead.company_name.ilike(f"%{company_name}%"))
    if industry:
        base = base.where(Lead.industry.ilike(f"%{industry}%"))
    if city:
        base = base.where(Lead.city.ilike(f"%{city}%"))
    if country:
        base = base.where(Lead.country.ilike(f"%{country}%"))
    if lead_source:
        base = base.where(Lead.lead_source.ilike(f"%{lead_source}%"))
    if campaign:
        base = base.where(Lead.campaign.ilike(f"%{campaign}%"))
    if lifecycle_stage:
        base = base.where(Lead.lifecycle_stage == lifecycle_stage)
    if lead_status:
        base = base.where(Lead.lead_status == lead_status)
    if priority:
        base = base.where(Lead.priority == priority)
    if owner_id is not None:
        base = base.where(Lead.owner_id == owner_id)
    if company_id is not None:
        base = base.where(Lead.company_id == company_id)
    if min_score is not None:
        base = base.where(Lead.lead_score >= min_score)
    if max_score is not None:
        base = base.where(Lead.lead_score <= max_score)
    if follow_up_before is not None:
        base = base.where(Lead.next_follow_up_at.isnot(None), Lead.next_follow_up_at <= follow_up_before)
    if overdue_follow_up is True:
        now = datetime.datetime.now(datetime.UTC)
        base = base.where(Lead.next_follow_up_at.isnot(None), Lead.next_follow_up_at < now)
    elif overdue_follow_up is False:
        now = datetime.datetime.now(datetime.UTC)
        base = base.where(
            (Lead.next_follow_up_at.is_(None)) | (Lead.next_follow_up_at >= now)
        )
    if has_email is True:
        base = base.where(Lead.email.isnot(None))
    elif has_email is False:
        base = base.where(Lead.email.is_(None))
    if has_phone is True:
        base = base.where(Lead.phone.isnot(None))
    elif has_phone is False:
        base = base.where(Lead.phone.is_(None))
    if converted is True:
        base = base.where(Lead.converted_at.isnot(None))
    elif converted is False:
        base = base.where(Lead.converted_at.is_(None))
    if do_not_contact is not None:
        base = base.where(Lead.do_not_contact.is_(do_not_contact))

    if tags:
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_names:
            tag_ids = [
                r[0]
                for r in (
                    await session.execute(select(Tag.id).where(Tag.name.in_(tag_names)))
                ).fetchall()
            ]
            if not tag_ids:
                return LeadListResponse(items=[], total=0, page=page, page_size=page_size)
            from nexus.database import LeadTag

            lead_ids = {
                r[0]
                for r in (
                    await session.execute(select(LeadTag.lead_id).where(LeadTag.tag_id.in_(tag_ids)))
                ).fetchall()
            }
            base = base.where(Lead.id.in_(list(lead_ids)))

    sort_col = _lead_sort_column(sort)
    base = base.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    result = await session.execute(base.offset((page - 1) * page_size).limit(page_size))
    leads = list(result.scalars().unique().all())

    return LeadListResponse(
        items=[_serialise(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


# NOTE: /leads/export must be registered before /leads/{lead_id}, otherwise
# FastAPI matches "export" against the integer path parameter.
@router.get("/leads/export")
async def export_leads(
    q: str = Query("", max_length=500),
    lifecycle_stage: str | None = Query(None, max_length=50),
    lead_status: str | None = Query(None, max_length=50),
    priority: str | None = Query(None, max_length=20),
    industry: str | None = Query(None, max_length=200),
    country: str | None = Query(None, max_length=100),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Lead).where(
        Lead.is_archived.is_(False) if archived is None else Lead.is_archived == archived
    )
    if q:
        base = base.where(Lead.search_filter(q))
    if lifecycle_stage:
        base = base.where(Lead.lifecycle_stage == lifecycle_stage)
    if lead_status:
        base = base.where(Lead.lead_status == lead_status)
    if priority:
        base = base.where(Lead.priority == priority)
    if industry:
        base = base.where(Lead.industry.ilike(f"%{industry}%"))
    if country:
        base = base.where(Lead.country.ilike(f"%{country}%"))

    result = await session.execute(base.order_by(Lead.updated_at.desc()))
    leads = list(result.scalars().unique().all())
    rows = [LeadExportRow.from_db(lead) for lead in leads]
    return {"rows": [r.model_dump() for r in rows], "count": len(rows)}


# ---------------------------------------------------------------------------
# Create / read / update
# ---------------------------------------------------------------------------


@router.post("/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    payload = body.model_dump(exclude={"tags"})
    lead = Lead(**payload, created_by_id=current_user.id)

    if lead.company_name or lead.company_domain:
        company = await _match_company(session, lead.company_name, lead.company_domain)
        if company:
            lead.company_id = company.id
    elif lead.company_id:
        company = await session.get(Company, lead.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    lead.data_quality_score = _lead_quality(body)
    session.add(lead)
    await session.flush()

    if body.tags:
        # Insert the association rows directly instead of assigning the
        # collection: on a freshly flushed row the relationship is unloaded, and
        # both reading and assigning it would trigger an implicit lazy load,
        # which async SQLAlchemy cannot perform.
        for tag_name in body.tags:
            tag = await _get_or_create_tag(session, tag_name)
            session.add(LeadTag(lead_id=lead.id, tag_id=tag.id))

    await _apply_score(session, lead)

    await record_activity(
        session,
        action="lead_created",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=f"Created lead {lead.display_name or lead.email or lead.id}",
        metadata={"email": lead.email, "source": lead.lead_source, "score": lead.lead_score},
    )
    await record_audit(
        session,
        action="create",
        entity_type="lead",
        entity_id=lead.id,
        user_id=current_user.id,
        after=snapshot(lead, _AUDIT_FIELDS),
    )
    await session.commit()
    await session.refresh(lead)
    return _serialise(lead)


@router.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return _serialise(lead)


@router.patch("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    body: LeadUpdate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    # Fetch with the tag collection eagerly loaded: replacing it later would
    # otherwise need an implicit lazy load that async SQLAlchemy cannot do.
    lead = (await session.execute(select(Lead).options(selectinload(Lead.tags)).where(Lead.id == lead_id))).scalars().first()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    update_data = body.model_dump(exclude_unset=True)
    rescore_flag = update_data.pop("rescore", None)
    tags = update_data.pop("tags", None)
    before = snapshot(lead, _AUDIT_FIELDS)

    if "company_id" in update_data and update_data["company_id"] is not None:
        if not await session.get(Company, update_data["company_id"]):
            raise HTTPException(status_code=404, detail="Company not found")

    company_linked = False
    if "company_name" in update_data or "company_domain" in update_data:
        company = await _match_company(
            session,
            update_data.get("company_name", lead.company_name),
            update_data.get("company_domain", lead.company_domain),
        )
        if company:
            lead.company_id = company.id
            company_linked = True

    if tags is not None:
        # ``tags`` is a replacement set, so resolve the names and assign once.
        lead.tags = [await _get_or_create_tag(session, tag_name) for tag_name in tags]

    for key, value in update_data.items():
        setattr(lead, key, value)

    # A renamed/cleared company that matches nothing must not keep pointing at
    # the previous record; the free-text name still shows.
    if ("company_name" in update_data or "company_domain" in update_data) and not company_linked:
        lead.company_id = None

    if "do_not_contact" in update_data and update_data["do_not_contact"]:
        # An opt-out is a hard stop: keep the caller's lifecycle state but make
        # it obvious why the lead is not being worked.
        if lead.lead_status not in ("Disqualified", "Nurture", "Converted"):
            lead.lead_status = "Nurture"

    touched_scored = bool(_SCORED_FIELDS & set(update_data))
    if update_data:
        lead.data_quality_score = _lead_quality(lead)

    await session.flush()
    if touched_scored or rescore_flag:
        await _apply_score(session, lead)

    after = snapshot(lead, _AUDIT_FIELDS)
    changed = {key for key in _AUDIT_FIELDS if before.get(key) != after.get(key)}
    if changed:
        await record_activity(
            session,
            action="lead_updated",
            user_id=current_user.id,
            entity_type="leads",
            entity_id=lead.id,
            description=f"Updated {len(changed)} field(s) on {lead.display_name or lead.email}",
            metadata={"changed": sorted(changed)},
        )
        await record_audit(
            session,
            action="update",
            entity_type="lead",
            entity_id=lead.id,
            user_id=current_user.id,
            before=before,
            after=snapshot(lead, _AUDIT_FIELDS),
        )
    await session.commit()
    await session.refresh(lead)
    return _serialise(lead)


@router.post("/leads/{lead_id}/rescore", response_model=LeadResponse)
async def rescore_lead(
    lead_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await _apply_score(session, lead)
    await record_activity(
        session,
        action="lead_rescored",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=f"Rescored lead {lead.display_name or lead.email} to {lead.lead_score}",
        metadata={"score": lead.lead_score},
    )
    await session.commit()
    await session.refresh(lead)
    return _serialise(lead)


# ---------------------------------------------------------------------------
# Archive / restore / delete
# ---------------------------------------------------------------------------


@router.post("/leads/{lead_id}/archive", response_model=LeadResponse)
async def archive_lead(
    lead_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.is_archived = True
    await record_activity(
        session,
        action="lead_archived",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=f"Archived lead {lead.display_name or lead.email}",
    )
    await session.commit()
    await session.refresh(lead)
    return _serialise(lead)


@router.post("/leads/{lead_id}/restore", response_model=LeadResponse)
async def restore_lead(
    lead_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.is_archived = False
    await record_activity(
        session,
        action="lead_restored",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=f"Restored lead {lead.display_name or lead.email}",
    )
    await session.commit()
    await session.refresh(lead)
    return _serialise(lead)


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await record_activity(
        session,
        action="lead_deleted",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=f"Deleted lead {lead.display_name or lead.email}",
    )
    await record_audit(
        session,
        action="delete",
        entity_type="lead",
        entity_id=lead.id,
        user_id=current_user.id,
        before=snapshot(lead, _AUDIT_FIELDS),
    )
    await session.delete(lead)
    await session.commit()


@router.post("/leads/bulk-tag", status_code=status.HTTP_200_OK)
async def bulk_tag_leads(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    lead_ids = body.get("lead_ids", [])
    tag_names = body.get("tags", [])
    if not lead_ids or not tag_names:
        raise HTTPException(status_code=400, detail="lead_ids and tags required")
    result = await session.execute(select(Lead).where(Lead.id.in_(lead_ids)))
    leads = list(result.scalars().unique().all())
    for tag_name in tag_names:
        tag = await _get_or_create_tag(session, tag_name)
        for lead in leads:
            if tag not in lead.tags:
                lead.tags.append(tag)
    await session.commit()
    return {"updated": len(leads), "tags": tag_names}


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@router.post("/leads/{lead_id}/convert", response_model=LeadConvertResponse)
async def convert_lead(
    lead_id: int,
    body: LeadConvertRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Promote a lead into a durable contact (and company).

    Matching rules, chosen by the caller:

    * ``auto`` — link when an existing contact (by email) or company (by name or
      domain) matches, otherwise create.
    * ``link`` — require a match (explicit id, or an email/domain match); a
      miss is a 404 rather than a silent create.
    * ``create`` — create, but refuse with 409 if a match already exists so a
      conversion can never produce a duplicate person or organisation.
    * ``none`` (company only) — leave the contact unlinked.

    A lead can be converted once; the link is preserved on the lead afterwards.
    """
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if lead.converted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This lead was already converted"
                f" (contact {lead.converted_contact_id}, at {lead.converted_at.isoformat()})."
                " Edit the existing records instead of converting twice."
            ),
        )
    if lead.is_archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restore this lead before converting it.",
        )

    contact_stage = body.contact_stage or "New"
    if contact_stage not in CRM_STAGES:
        raise HTTPException(status_code=422, detail=f"contact_stage must be one of: {', '.join(CRM_STAGES)}")

    # ---- Company side ----------------------------------------------------
    company: Company | None = None
    created_company = False
    existing_company: Company | None = None
    if body.company_mode != "none":
        if body.company_id is not None:
            company = await session.get(Company, body.company_id)
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
        else:
            existing_company = await _match_company(session, lead.company_name, lead.company_domain)
            if body.company_mode == "link":
                if not existing_company:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "No company matches this lead's name or domain."
                            " Pass company_id, or use company_mode='create'."
                        ),
                    )
                company = existing_company
            elif body.company_mode == "create":
                if existing_company:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"A company matching this lead already exists (id {existing_company.id},"
                            f" '{existing_company.name}'). Link it instead of creating a duplicate."
                        ),
                    )
                company = None
            else:  # auto
                company = existing_company

        if company is None and body.company_mode in ("auto", "create"):
            company = Company(
                name=lead.company_name or lead.display_name or f"Lead {lead.id}",
                domain=lead.company_domain,
                website=lead.website,
                industry=lead.industry,
                employee_count=lead.employee_count,
                company_size=lead.company_size,
                city=lead.city,
                state=lead.state,
                country=lead.country,
                source=lead.lead_source,
                created_by_id=current_user.id,
            )
            session.add(company)
            await session.flush()
            created_company = True

    if company is not None and body.fill_missing_fields and not created_company:
        # Fill only blanks: a conversion must never overwrite curated data.
        for field_name, value in (
            ("industry", lead.industry),
            ("employee_count", lead.employee_count),
            ("company_size", lead.company_size),
            ("city", lead.city),
            ("state", lead.state),
            ("country", lead.country),
            ("domain", lead.company_domain),
            ("website", lead.website),
        ):
            if value not in (None, "", []) and getattr(company, field_name, None) in (None, ""):
                setattr(company, field_name, value)

    # ---- Contact side ----------------------------------------------------
    contact: Contact | None = None
    created_contact = False
    if body.contact_id is not None:
        contact = await session.get(Contact, body.contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
    else:
        existing_contact = await _match_contact(session, lead.email)
        if body.contact_mode == "link":
            if not existing_contact:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No contact matches this lead's email address."
                        " Pass contact_id, or use contact_mode='create'."
                    ),
                )
            contact = existing_contact
        elif body.contact_mode == "create":
            if existing_contact:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"A contact with this email already exists (id {existing_contact.id})."
                        " Link it instead of creating a duplicate."
                    ),
                )
        else:  # auto
            contact = existing_contact

        if contact is None:
            contact = Contact(
                first_name=lead.first_name,
                last_name=lead.last_name,
                full_name=lead.full_name,
                job_title=lead.job_title,
                department=lead.department,
                seniority=lead.seniority,
                email=lead.email,
                email_status=lead.email_status,
                phone=lead.phone,
                phone_status=lead.phone_status,
                linkedin_url=lead.linkedin_url,
                company_name=company.name if company else lead.company_name,
                company_id=company.id if company else None,
                city=lead.city,
                country=lead.country,
                source=lead.lead_source or "Lead conversion",
                notes=body.note or None,
                stage=contact_stage,
                skills=[],
                employment_history=[],
                created_by_id=current_user.id,
            )
            # Set the relationship object, not just the id: the response model
            # serialises ``contact.company``.
            contact.company = company
            session.add(contact)
            await session.flush()
            created_contact = True

    if not created_contact:
        if body.fill_missing_fields:
            for field_name, value in (
                ("first_name", lead.first_name),
                ("last_name", lead.last_name),
                ("job_title", lead.job_title),
                ("department", lead.department),
                ("seniority", lead.seniority),
                ("email", lead.email),
                ("phone", lead.phone),
                ("linkedin_url", lead.linkedin_url),
                ("city", lead.city),
                ("country", lead.country),
            ):
                if value not in (None, "") and getattr(contact, field_name, None) in (None, ""):
                    setattr(contact, field_name, value)
        if company is not None and contact.company_id is None:
            contact.company_id = company.id
            if not contact.company_name:
                contact.company_name = company.name
        if body.note:
            contact.notes = f"{contact.notes}\n{body.note}".strip() if contact.notes else body.note
        if body.contact_stage:
            contact.stage = contact_stage

    contact.data_quality_score = contact_quality(contact)
    if company is not None:
        await attach_contact_counts_for_company(session, company)
        company.data_quality_score = company_quality(company, contact_count=company.contact_count or 0)

    # ---- Lead side -------------------------------------------------------
    lead.converted_contact_id = contact.id
    lead.converted_company_id = company.id if company else None
    lead.converted_at = datetime.datetime.now(datetime.UTC)
    lead.lead_status = "Converted"
    lead.lifecycle_stage = "Converted"
    if company is not None:
        lead.company_id = company.id

    await session.flush()

    await record_activity(
        session,
        action="lead_converted",
        user_id=current_user.id,
        entity_type="leads",
        entity_id=lead.id,
        description=(
            f"Converted lead {lead.display_name or lead.email} to contact {contact.id}"
            + (f" and company {company.id}" if company else "")
        ),
        metadata={
            "contact_id": contact.id,
            "company_id": company.id if company else None,
            "created_contact": created_contact,
            "created_company": created_company,
        },
    )
    await record_audit(
        session,
        action="convert",
        entity_type="lead",
        entity_id=lead.id,
        user_id=current_user.id,
        before={"converted_at": None, "lead_status": "New"},
        after=snapshot(lead, _AUDIT_FIELDS),
    )
    await record_activity(
        session,
        action="contact_created" if created_contact else "contact_linked_from_lead",
        user_id=current_user.id,
        entity_type="contacts",
        entity_id=contact.id,
        description=f"{'Created' if created_contact else 'Linked'} contact {contact.display_name or contact.email} from lead {lead.id}",
    )

    await session.commit()
    await session.refresh(lead)
    await session.refresh(contact)
    if company is not None:
        await session.refresh(company)

    return LeadConvertResponse(
        lead=_serialise(lead),
        contact=ContactResponse.model_validate(contact),
        company=CompanyResponse.model_validate(company) if company else None,
        created_contact=created_contact,
        created_company=created_company,
    )
