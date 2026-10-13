from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import CRM_STAGES, ActivityLog, Company, Contact, FollowUpTask, ImportJob

router = APIRouter(tags=["analytics"])


def utcnow() -> datetime:
    """Current time, always timezone-aware UTC."""
    return datetime.now(UTC)


@router.get("/analytics/overview")
async def analytics_overview(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    company_count = (
        await session.execute(select(func.count(Company.id)).where(Company.is_archived.is_(False)))
    ).scalar() or 0
    contact_count = (
        await session.execute(select(func.count(Contact.id)).where(Contact.is_archived.is_(False)))
    ).scalar() or 0
    email_avail = (
        await session.execute(
            select(func.count(Contact.id)).where(Contact.email.isnot(None), Contact.is_archived.is_(False))
        )
    ).scalar() or 0
    phone_avail = (
        await session.execute(
            select(func.count(Contact.id)).where(Contact.phone.isnot(None), Contact.is_archived.is_(False))
        )
    ).scalar() or 0
    linkedin_avail = (
        await session.execute(
            select(func.count(Contact.id)).where(Contact.linkedin_url.isnot(None), Contact.is_archived.is_(False))
        )
    ).scalar() or 0
    verified_email = await session_execute_count(session, Contact, Contact.email_status == "verified")
    needs_review = await session_execute_count(
        session, Contact, Contact.data_quality_score < 50, Contact.is_archived.is_(False)
    )

    return {
        "companies": company_count,
        "contacts": contact_count,
        "emails_available": email_avail,
        "phones_available": phone_avail,
        "linkedin_profiles": linkedin_avail,
        "verified_emails": verified_email,
        "records_needing_review": needs_review,
    }


@router.get("/analytics/pipeline")
async def pipeline_summary(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Contacts per CRM stage plus open/overdue follow-up counts for the Pipeline page."""
    rows = (
        await session.execute(
            select(Contact.stage, func.count(Contact.id))
            .where(Contact.is_archived.is_(False))
            .group_by(Contact.stage)
        )
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    stages = [{"stage": s, "count": counts.get(s, 0)} for s in CRM_STAGES]
    open_tasks = (
        await session.execute(select(func.count(FollowUpTask.id)).where(FollowUpTask.done.is_(False)))
    ).scalar() or 0
    overdue_tasks = (
        await session.execute(
            select(func.count(FollowUpTask.id)).where(
                FollowUpTask.done.is_(False),
                FollowUpTask.due_at.isnot(None),
                FollowUpTask.due_at < utcnow(),
            )
        )
    ).scalar() or 0
    return {"stages": stages, "open_tasks": open_tasks, "overdue_tasks": overdue_tasks}


async def session_execute_count(session: AsyncSession, model, *predicates) -> int:
    stmt = select(func.count(model.id))
    for p in predicates:
        stmt = stmt.where(p)
    result = await session.execute(stmt)
    return result.scalar() or 0


@router.get("/analytics/growth")
async def growth_chart(
    days: int = Query(90, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    since = utcnow() - timedelta(days=days)
    stmt = (
        select(func.date(Company.created_at).label("date"), func.count(Company.id).label("companies"))
        .where(Company.created_at >= since, Company.is_archived.is_(False))
        .group_by(func.date(Company.created_at))
        .order_by(func.date(Company.created_at))
    )
    result = await session.execute(stmt)
    company_series = [{"date": r.date if r.date else "", "companies": r.companies} for r in result.fetchall()]

    stmt = (
        select(func.date(Contact.created_at).label("date"), func.count(Contact.id).label("contacts"))
        .where(Contact.created_at >= since, Contact.is_archived.is_(False))
        .group_by(func.date(Contact.created_at))
        .order_by(func.date(Contact.created_at))
    )
    result = await session.execute(stmt)
    contact_series = [{"date": r.date if r.date else "", "contacts": r.contacts} for r in result.fetchall()]

    return {"days": days, "company_series": company_series, "contact_series": contact_series}


@router.get("/analytics/companies-by-industry")
async def companies_by_industry(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Company.industry, func.count(Company.id))
        .where(Company.industry.isnot(None), Company.is_archived.is_(False))
        .group_by(Company.industry)
        .order_by(func.count(Company.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"industry": r.industry, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/companies-by-size")
async def companies_by_size(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Company.company_size, func.count(Company.id))
        .where(Company.company_size.isnot(None), Company.is_archived.is_(False))
        .group_by(Company.company_size)
        .order_by(func.count(Company.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"size": r.company_size, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/contacts-by-department")
async def contacts_by_department(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Contact.department, func.count(Contact.id))
        .where(Contact.department.isnot(None), Contact.is_archived.is_(False))
        .group_by(Contact.department)
        .order_by(func.count(Contact.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"department": r.department, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/contacts-by-seniority")
async def contacts_by_seniority(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Contact.seniority, func.count(Contact.id))
        .where(Contact.seniority.isnot(None), Contact.is_archived.is_(False))
        .group_by(Contact.seniority)
        .order_by(func.count(Contact.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"seniority": r.seniority, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/contacts-by-country")
async def contacts_by_country(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Contact.country, func.count(Contact.id))
        .where(Contact.country.isnot(None), Contact.is_archived.is_(False))
        .group_by(Contact.country)
        .order_by(func.count(Contact.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"country": r.country, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/contacts-by-city")
async def contacts_by_city(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Contact.city, func.count(Contact.id))
        .where(Contact.city.isnot(None), Contact.is_archived.is_(False))
        .group_by(Contact.city)
        .order_by(func.count(Contact.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    return [{"city": r.city, "count": r.count} for r in result.fetchall()]


@router.get("/analytics/email-coverage")
async def email_coverage(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    total = await session_execute_count(session, Contact, Contact.is_archived.is_(False))
    with_email = await session_execute_count(
        session, Contact, Contact.email.isnot(None), Contact.is_archived.is_(False)
    )
    verified = await session_execute_count(
        session, Contact, Contact.email_status == "verified", Contact.is_archived.is_(False)
    )
    return {
        "total_contacts": total,
        "with_email": with_email,
        "verified": verified,
        "missing": total - with_email,
        "coverage_pct": round((with_email / max(1, total)) * 100, 1),
    }


@router.get("/analytics/phone-coverage")
async def phone_coverage(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    total = await session_execute_count(session, Contact, Contact.is_archived.is_(False))
    with_phone = await session_execute_count(
        session, Contact, Contact.phone.isnot(None), Contact.is_archived.is_(False)
    )
    return {
        "total_contacts": total,
        "with_phone": with_phone,
        "missing": total - with_phone,
        "coverage_pct": round((with_phone / max(1, total)) * 100, 1),
    }


@router.get("/analytics/linkedin-coverage")
async def linkedin_coverage(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    total = await session_execute_count(session, Contact, Contact.is_archived.is_(False))
    with_linkedin = await session_execute_count(
        session, Contact, Contact.linkedin_url.isnot(None), Contact.is_archived.is_(False)
    )
    return {
        "total_contacts": total,
        "with_linkedin": with_linkedin,
        "missing": total - with_linkedin,
        "coverage_pct": round((with_linkedin / max(1, total)) * 100, 1),
    }


@router.get("/analytics/verification-status")
async def verification_status(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(Contact.last_verified.isnot(None).label("verified"), func.count(Contact.id).label("count"))
        .where(Contact.is_archived.is_(False))
        .group_by(Contact.last_verified.isnot(None))
    )
    result = await session.execute(stmt)
    verified = 0
    unverified = 0
    for r in result.fetchall():
        if bool(r.verified):
            verified = r.count
        else:
            unverified = r.count
    return {"verified": verified, "unverified": unverified, "total": verified + unverified}


@router.get("/analytics/import-performance")
async def import_performance(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(ImportJob)
        .where(ImportJob.status == "completed", ImportJob.created_by_id == current_user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    jobs = list(result.scalars().unique().all())
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "rows_total": j.rows_total,
            "rows_added": j.rows_added,
            "rows_updated": j.rows_updated,
            "rows_duplicate": j.rows_duplicate,
            "rows_invalid": j.rows_invalid,
            "rows_skipped": j.rows_skipped,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.get("/analytics/activity-narrative")
async def activity_narrative(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.created_at >= utcnow() - timedelta(days=7))
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
    )
    result = await session.execute(stmt)
    activities = list(result.scalars().unique().all())
    return [
        {
            "id": a.id,
            "action": a.action,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities
    ]
