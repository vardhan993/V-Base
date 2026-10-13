from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity, record_audit, snapshot
from nexus.core.counts import attach_contact_counts, attach_contact_counts_for_company
from nexus.core.db import get_session
from nexus.database import Company, CompanyTag, Tag
from nexus.schemas.company import (
    CompanyCreate,
    CompanyExportRow,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)

#: Columns captured in audit log before/after payloads. Never includes
#: relationships, so no unbounded or sensitive data is written.
_AUDIT_FIELDS = [
    "name",
    "website",
    "domain",
    "linkedin_url",
    "industry",
    "employee_count",
    "city",
    "country",
    "data_quality_score",
    "is_archived",
]

router = APIRouter(tags=["companies"])


@router.get("/companies")
async def list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=500),
    industry: str | None = Query(None, max_length=200),
    country: str | None = Query(None, max_length=100),
    city: str | None = Query(None, max_length=100),
    employee_min: int | None = Query(None, ge=0),
    employee_max: int | None = Query(None, ge=0),
    funding_stage: str | None = Query(None, max_length=100),
    company_size: str | None = Query(None, max_length=100),
    tags: str = Query("", max_length=500),
    sort: str = Query("updated_at"),
    order: str = Query("desc"),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Company).where(
        Company.is_archived.is_(False) if archived is None else Company.is_archived == archived
    )

    if q:
        base = base.where(Company.search_filter(q))
    if industry:
        base = base.where(Company.industry.ilike(f"%{industry}%"))
    if country:
        base = base.where(Company.country.ilike(f"%{country}%"))
    if city:
        base = base.where(Company.city.ilike(f"%{city}%"))
    if employee_min is not None:
        base = base.where(Company.employee_count >= employee_min)
    if employee_max is not None:
        base = base.where(Company.employee_count <= employee_max)
    if funding_stage:
        base = base.where(Company.funding_stage.ilike(f"%{funding_stage}%"))
    if company_size:
        base = base.where(Company.company_size.ilike(f"%{company_size}%"))

    if tags:
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_names:
            tag_stmt = select(Tag.id).where(Tag.name.in_(tag_names))
            tag_result = await session.execute(tag_stmt)
            tag_ids = [r[0] for r in tag_result.fetchall()]
            if tag_ids:
                ct_stmt = select(CompanyTag.company_id).where(CompanyTag.tag_id.in_(tag_ids))
                ct_result = await session.execute(ct_stmt)
                company_ids = {r[0] for r in ct_result.fetchall()}
                base = base.where(Company.id.in_(list(company_ids)))

    sort_col = _company_sort_column(sort)
    base = base.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    base = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(base)
    companies = list(result.scalars().unique().all())
    await attach_contact_counts(session, companies)

    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        page_size=page_size,
    )


def _company_sort_column(sort: str):
    mapping = {
        "updated_at": Company.updated_at,
        "created_at": Company.created_at,
        "name": Company.name,
        "employee_count": Company.employee_count,
        "data_quality_score": Company.data_quality_score,
    }
    return mapping.get(sort, Company.updated_at)


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = Company(**body.model_dump(), created_by_id=current_user.id, data_quality_score=_company_quality(body))
    session.add(company)
    await session.flush()
    await record_activity(
        session,
        action="company_created",
        user_id=current_user.id,
        entity_type="companies",
        entity_id=company.id,
        description=f"Created company {company.name}",
        metadata={"name": company.name, "domain": company.domain},
    )
    await record_audit(
        session,
        action="create",
        entity_type="company",
        entity_id=company.id,
        user_id=current_user.id,
        after=snapshot(company, _AUDIT_FIELDS),
    )
    await session.commit()
    await session.refresh(company)
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.get("/companies/export")
async def export_companies(
    industry: str | None = Query(None),
    country: str | None = Query(None),
    city: str | None = Query(None),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> dict:
    base = select(Company).where(
        Company.is_archived.is_(False) if archived is None else Company.is_archived == archived
    )
    if industry:
        base = base.where(Company.industry.ilike(f"%{industry}%"))
    if country:
        base = base.where(Company.country.ilike(f"%{country}%"))
    if city:
        base = base.where(Company.city.ilike(f"%{city}%"))
    result = await session.execute(base.order_by(Company.updated_at.desc()))
    companies = list(result.scalars().unique().all())
    rows = []
    for company in companies:
        rows.append(CompanyExportRow.from_db(company))
    return {"rows": [r.model_dump() for r in rows], "count": len(rows)}


@router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = await session.get(Company, company_id)
    if not company or company.is_archived and current_user.is_superuser is False:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: int,
    body: CompanyUpdate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    company = await session.get(Company, company_id)
    if not company or company.is_archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    update_data = body.model_dump(exclude_unset=True)
    before = snapshot(company, _AUDIT_FIELDS)
    for key, value in update_data.items():
        if key == "tags":
            existing = {t.id for t in company.tags}
            incoming = set()
            for tag_name in value:
                tag = await _get_or_create_tag(session, tag_name)
                incoming.add(tag.id)
                company.tags.append(tag)
            for tid in list(existing):
                if tid not in incoming:
                    company.tags = [t for t in company.tags if t.id != tid]
        else:
            setattr(company, key, value)
    company.data_quality_score = _company_quality(company)
    await session.flush()
    changed = _diff_fields(before, snapshot(company, _AUDIT_FIELDS))
    if changed:
        await record_activity(
            session,
            action="company_updated",
            user_id=current_user.id,
            entity_type="companies",
            entity_id=company.id,
            description=f"Updated {len(changed)} field(s) on {company.name}",
            metadata={"changed": sorted(changed)},
        )
        await record_audit(
            session,
            action="update",
            entity_type="company",
            entity_id=company.id,
            user_id=current_user.id,
            before=before,
            after=snapshot(company, _AUDIT_FIELDS),
        )
    await session.commit()
    await session.refresh(company)
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.post("/companies/{company_id}/archive", response_model=CompanyResponse)
async def archive_company(
    company_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    company.is_archived = True
    await record_activity(
        session,
        action="company_archived",
        user_id=current_user.id,
        entity_type="companies",
        entity_id=company.id,
        description=f"Archived company {company.name}",
    )
    await record_audit(
        session,
        action="archive",
        entity_type="company",
        entity_id=company.id,
        user_id=current_user.id,
        before={"is_archived": False},
        after={"is_archived": True},
    )
    await session.commit()
    await session.refresh(company)
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.post("/companies/{company_id}/restore", response_model=CompanyResponse)
async def restore_company(
    company_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    company.is_archived = False
    await record_activity(
        session,
        action="company_restored",
        user_id=current_user.id,
        entity_type="companies",
        entity_id=company.id,
        description=f"Restored company {company.name}",
    )
    await session.commit()
    await session.refresh(company)
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    await record_audit(
        session,
        action="delete",
        entity_type="company",
        entity_id=company.id,
        user_id=current_user.id,
        before=snapshot(company, _AUDIT_FIELDS),
    )
    await session.delete(company)
    await session.commit()


@router.post("/companies/bulk-tag", status_code=status.HTTP_200_OK)
async def bulk_tag_companies(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company_ids = body.get("company_ids", [])
    tag_names = body.get("tags", [])
    if not company_ids or not tag_names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_ids and tags required")
    result = await session.execute(select(Company).where(Company.id.in_(company_ids)))
    companies = list(result.scalars().unique().all())
    for tag_name in tag_names:
        tag = await _get_or_create_tag(session, tag_name)
        for company in companies:
            if tag not in company.tags:
                company.tags.append(tag)
    await session.commit()
    return {"updated": len(companies), "tags": tag_names}


async def _get_or_create_tag(session: AsyncSession, name: str) -> Tag:
    stmt = select(Tag).where(Tag.name == name)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name, kind="company")
        session.add(tag)
        await session.flush()
    return tag


def _diff_fields(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """Field names whose value changed between two audit snapshots."""
    return {key for key in after if before.get(key) != after.get(key)}


def _company_quality(company: Company | CompanyCreate) -> int:
    score = 0
    if company.name:
        score += 10
    if company.website:
        score += 10
    if company.domain:
        score += 5
    if company.linkedin_url:
        score += 10
    if company.industry:
        score += 5
    if company.city:
        score += 5
    if company.country:
        score += 5
    if company.employee_count is not None:
        score += 5
    if company.founded_year is not None:
        score += 5
    if company.technologies:
        score += 5
    if isinstance(company, Company):
        if company.contacts:
            score += min(15, len(company.contacts) * 3)
    return min(100, score)
