from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Company, Contact

router = APIRouter(tags=["data-quality"])


@router.get("/quality/summary")
async def quality_summary(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    total_contacts = (await session.execute(select(func.count(Contact.id)))).scalar() or 0
    total_companies = (await session.execute(select(func.count(Company.id)))).scalar() or 0
    contacts_with_email = (
        await session.execute(select(func.count(Contact.id)).where(Contact.email.isnot(None)))
    ).scalar() or 0
    contacts_with_phone = (
        await session.execute(select(func.count(Contact.id)).where(Contact.phone.isnot(None)))
    ).scalar() or 0
    contacts_with_linkedin = (
        await session.execute(select(func.count(Contact.id)).where(Contact.linkedin_url.isnot(None)))
    ).scalar() or 0
    contacts_with_company = (
        await session.execute(select(func.count(Contact.id)).where(Contact.company_id.isnot(None)))
    ).scalar() or 0
    contacts_invalid_email = await _count_invalid_email(session)
    contacts_phone_no_country_code = await _count_phone_without_country_code(session)
    companies_missing_domain = await _count_missing(session, Company, "domain")
    companies_missing_website = await _count_missing(session, Company, "website")
    companies_missing_linkedin = await _count_missing(session, Company, "linkedin_url")
    contacts_missing_job_title = await _count_missing(session, Contact, "job_title")
    contacts_missing_phone = await _count_missing(session, Contact, "phone")
    contacts_missing_linkedin = await _count_missing(session, Contact, "linkedin_url")
    stale_contacts = await _count_stale(session, Contact)
    stale_companies = await _count_stale(session, Company)

    return {
        "contacts": {
            "total": total_contacts,
            "with_email": contacts_with_email,
            "with_phone": contacts_with_phone,
            "with_linkedin": contacts_with_linkedin,
            "with_company": contacts_with_company,
            "invalid_email": contacts_invalid_email,
            "phone_missing_country_code": contacts_phone_no_country_code,
            "missing_job_title": contacts_missing_job_title,
            "missing_phone": contacts_missing_phone,
            "missing_linkedin": contacts_missing_linkedin,
            "stale": stale_contacts,
        },
        "companies": {
            "total": total_companies,
            "missing_domain": companies_missing_domain,
            "missing_website": companies_missing_website,
            "missing_linkedin": companies_missing_linkedin,
            "stale": stale_companies,
        },
    }


async def _count_invalid_email(session: AsyncSession) -> int:
    from sqlalchemy import func

    stmt = select(func.count(Contact.id)).where(Contact.email.isnot(None), Contact.email.notlike("%@%"))
    result = await session.execute(stmt)
    return result.scalar() or 0


async def _count_phone_without_country_code(session: AsyncSession) -> int:
    """Contacts whose phone has no explicit international prefix.

    A stored number without a leading ``+`` cannot be placed in any country,
    so it is counted separately from merely missing or malformed numbers.
    """
    stmt = select(func.count(Contact.id)).where(Contact.phone.isnot(None), Contact.phone.notlike("+%"))
    result = await session.execute(stmt)
    return result.scalar() or 0


async def _count_missing(session: AsyncSession, model, column_name: str) -> int:
    col = getattr(model, column_name)
    stmt = select(func.count(model.id)).where(col.is_(None))
    result = await session.execute(stmt)
    return result.scalar() or 0


async def _count_stale(session: AsyncSession, model) -> int:
    stmt = select(func.count(model.id)).where(model.last_verified.is_(None))
    result = await session.execute(stmt)
    return result.scalar() or 0


@router.get("/quality/contacts/needs-review")
async def contacts_needing_review(
    missing_email: bool = Query(True),
    missing_phone: bool = Query(True),
    missing_linkedin: bool = Query(True),
    missing_company: bool = Query(True),
    invalid_email: bool = Query(True),
    phone_missing_country_code: bool = Query(True),
    low_score: int | None = Query(50, ge=0, le=100),
    stale: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Contact).where(Contact.is_archived.is_(False))

    conditions = []
    if missing_email:
        conditions.append(Contact.email.is_(None))
    if missing_phone:
        conditions.append(Contact.phone.is_(None))
    if missing_linkedin:
        conditions.append(Contact.linkedin_url.is_(None))
    if missing_company:
        conditions.append(Contact.company_id.is_(None))
    if invalid_email:
        conditions.append(and_(Contact.email.isnot(None), Contact.email.notlike("%@%")))
    if phone_missing_country_code:
        conditions.append(and_(Contact.phone.isnot(None), Contact.phone.notlike("+%")))
    if low_score is not None:
        conditions.append(Contact.data_quality_score < low_score)
    if stale:
        conditions.append(Contact.last_verified.is_(None))

    # A contact belongs on the review list when it matches ANY of the
    # enabled issue criteria, not all of them at once.
    if conditions:
        base = base.where(or_(*conditions))
    base = base.order_by(Contact.updated_at.desc()).limit(500)
    result = await session.execute(base)
    contacts = list(result.scalars().unique().all())
    return [
        {
            "id": c.id,
            "name": c.display_name,
            "email": c.email,
            "phone": c.phone,
            "linkedin_url": c.linkedin_url,
            "company_name": c.company_name,
            "data_quality_score": c.data_quality_score,
            "last_verified": c.last_verified.isoformat() if c.last_verified else None,
        }
        for c in contacts
    ]
