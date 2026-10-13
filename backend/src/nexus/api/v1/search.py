from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Company, Contact, SavedSearch, Tag

router = APIRouter(tags=["search"])


@router.get("/search/global")
async def global_search(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=100),
    entity: str = Query("all", pattern="^(all|companies|contacts)$"),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    results = {"companies": [], "contacts": [], "total": 0}

    if entity in ("all", "companies"):
        stmt = select(Company).where(Company.search_filter(q))
        stmt = stmt.order_by(Company.updated_at.desc()).limit(limit)
        result = await session.execute(stmt)
        companies = list(result.scalars().unique().all())
        results["companies"] = [
            {
                "id": c.id,
                "name": c.name,
                "type": "company",
                "subtitle": c.city or c.industry or "",
                "fields": {
                    "name": c.name,
                    "domain": c.domain,
                    "website": c.website,
                    "industry": c.industry,
                    "headcount": c.employee_count,
                    "size": c.company_size,
                    "city": c.city,
                    "country": c.country,
                    "linkedin_url": c.linkedin_url,
                    "technologies": ", ".join(c.technologies or []),
                },
            }
            for c in companies
        ]
        results["total"] += len(companies)

    if entity in ("all", "contacts"):
        stmt = select(Contact).where(Contact.search_filter(q))
        stmt = stmt.order_by(Contact.updated_at.desc()).limit(limit)
        result = await session.execute(stmt)
        contacts = list(result.scalars().unique().all())
        results["contacts"] = [
            {
                "id": c.id,
                "name": c.display_name,
                "type": "contact",
                "subtitle": c.job_title or c.company_name or "",
                "fields": {
                    "first_name": c.first_name,
                    "last_name": c.last_name,
                    "full_name": c.full_name,
                    "job_title": c.job_title,
                    "department": c.department,
                    "seniority": c.seniority,
                    "email": c.email,
                    "phone": c.phone,
                    "linkedin_url": c.linkedin_url,
                    "company_name": c.company_name,
                },
            }
            for c in contacts
        ]
        results["total"] += len(contacts)

    return results


@router.get("/search/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    suggestions = {"companies": [], "contacts": [], "tags": [], "industries": [], "cities": []}

    if len(q) >= 2:
        stmt = select(Company).where(Company.name.ilike(f"%{q}%")).limit(6)
        result = await session.execute(stmt)
        suggestions["companies"] = [{"id": c.id, "name": c.name} for c in result.scalars().unique().all()]

        stmt = select(Contact).where(Contact.full_name.ilike(f"%{q}%")).limit(6)
        result = await session.execute(stmt)
        suggestions["contacts"] = [{"id": c.id, "name": c.display_name} for c in result.scalars().unique().all()]

        stmt = select(Tag).where(Tag.name.ilike(f"%{q}%")).limit(6)
        result = await session.execute(stmt)
        suggestions["tags"] = [{"id": t.id, "name": t.name} for t in result.scalars().unique().all()]

        stmt = select(Company.industry).where(Company.industry.ilike(f"%{q}%"), Company.industry.isnot(None)).limit(6)
        result = await session.execute(stmt)
        suggestions["industries"] = [r[0] for r in result.fetchall() if r[0]]

        stmt = select(Contact.city).where(Contact.city.ilike(f"%{q}%"), Contact.city.isnot(None)).limit(6)
        result = await session.execute(stmt)
        suggestions["cities"] = [r[0] for r in result.fetchall() if r[0]]

    return suggestions


@router.get("/search/recent")
async def recent_searches(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = (
        select(SavedSearch)
        .where(SavedSearch.created_by_id == current_user.id)
        .order_by(SavedSearch.created_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    searches = list(result.scalars().unique().all())
    return [
        {
            "id": s.id,
            "name": s.name,
            "query": s.query,
            "scope": s.scope,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in searches
    ]


@router.post("/search/saved", status_code=status.HTTP_201_CREATED)
async def save_search(
    body: dict[str, str], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    search = SavedSearch(
        name=body.get("name", "Saved search"),
        query=body.get("query"),
        filters=body.get("filters", []),
        scope=body.get("scope"),
        created_by_id=current_user.id,
    )
    session.add(search)
    await session.flush()
    await session.refresh(search)
    await session.commit()
    return {
        "id": search.id,
        "name": search.name,
        "query": search.query,
        "scope": search.scope,
        "created_at": search.created_at.isoformat() if search.created_at else None,
    }


@router.delete("/search/saved/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_search(
    search_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    search = await session.get(SavedSearch, search_id)
    if not search or search.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    await session.delete(search)
    await session.commit()
