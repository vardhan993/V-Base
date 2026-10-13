from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Company, Contact, ContactList, ListCompany, ListContact

router = APIRouter(tags=["lists"])


@router.get("/lists")
async def list_lists(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = select(ContactList).order_by(ContactList.name)
    result = await session.execute(stmt)
    lists = list(result.scalars().unique().all())
    contact_counts = dict(
        (await session.execute(select(ListContact.list_id, func.count()).group_by(ListContact.list_id))).all()
    )
    company_counts = dict(
        (await session.execute(select(ListCompany.list_id, func.count()).group_by(ListCompany.list_id))).all()
    )
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "kind": item.kind,
            "contact_count": contact_counts.get(item.id, 0),
            "company_count": company_counts.get(item.id, 0),
        }
        for item in lists
    ]


@router.post("/lists", status_code=status.HTTP_201_CREATED)
async def create_list(
    body: dict[str, str], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    existing = (
        await session.execute(select(ContactList).where(func.lower(ContactList.name) == name.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"List '{existing.name}' already exists")

    list_obj = ContactList(
        name=name, description=body.get("description"), kind=body.get("kind"), created_by_id=current_user.id
    )
    session.add(list_obj)
    await session.flush()
    await session.refresh(list_obj)
    await session.commit()
    return {"id": list_obj.id, "name": list_obj.name, "description": list_obj.description, "kind": list_obj.kind}


@router.patch("/lists/{list_id}", status_code=status.HTTP_200_OK)
async def update_list(
    list_id: int,
    body: dict[str, str],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be blank")
        clash = (
            await session.execute(
                select(ContactList).where(func.lower(ContactList.name) == new_name.lower(), ContactList.id != list_id)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"List '{clash.name}' already exists")
        list_obj.name = new_name
    if "description" in body:
        list_obj.description = body["description"]
    if "kind" in body:
        list_obj.kind = body["kind"]
    await session.commit()
    await session.refresh(list_obj)
    return {"id": list_obj.id, "name": list_obj.name, "description": list_obj.description, "kind": list_obj.kind}


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(
    list_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    await session.delete(list_obj)
    await session.commit()


@router.post("/lists/{list_id}/contacts", status_code=status.HTTP_200_OK)
async def add_contacts_to_list(
    list_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    contact_ids = body.get("contact_ids", [])
    if not contact_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_ids required")
    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    result = await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))
    contacts = list(result.scalars().unique().all())
    added = 0
    for contact in contacts:
        exists = await session.execute(
            select(ListContact).where(ListContact.list_id == list_id, ListContact.contact_id == contact.id)
        )
        if not exists.scalar_one_or_none():
            session.add(ListContact(list_id=list_id, contact_id=contact.id))
            added += 1
    await session.commit()
    return {"added": added, "total": len(contacts)}


@router.delete("/lists/{list_id}/contacts", status_code=status.HTTP_200_OK)
async def remove_contacts_from_list(
    list_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    contact_ids = body.get("contact_ids", [])
    if not contact_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_ids required")
    result = await session.execute(
        select(ListContact).where(ListContact.list_id == list_id, ListContact.contact_id.in_(contact_ids))
    )
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return {"removed": len(rows)}


@router.get("/lists/{list_id}/contacts")
@router.get("/lists/{list_id}/companies")
async def list_list_items(
    list_id: int,
    kind: str = "contacts",
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    if kind == "companies":
        base = (
            select(Company)
            .where(Company.id.in_(select(ListCompany.company_id).where(ListCompany.list_id == list_id)))
            .order_by(Company.updated_at.desc())
        )
        total_stmt = select(ListCompany.company_id).where(ListCompany.list_id == list_id)
        total_result = await session.execute(total_stmt)
        total = len(list(total_result.scalars().all()))
        base = base.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(base)
        companies = list(result.scalars().unique().all())
        return {
            "items": [
                {
                    "id": c.id,
                    "name": c.name,
                    "domain": c.domain,
                    "industry": c.industry,
                    "country": c.country,
                    "data_quality_score": c.data_quality_score,
                }
                for c in companies
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    base = (
        select(Contact)
        .where(Contact.id.in_(select(ListContact.contact_id).where(ListContact.list_id == list_id)))
        .order_by(Contact.updated_at.desc())
    )
    total_stmt = select(ListContact.contact_id).where(ListContact.list_id == list_id)
    total_result = await session.execute(total_stmt)
    total = len(list(total_result.scalars().all()))
    base = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(base)
    contacts = list(result.scalars().unique().all())
    return {
        "items": [
            {
                "id": c.id,
                "name": c.display_name,
                "job_title": c.job_title,
                "email": c.email,
                "company_name": c.company_name,
            }
            for c in contacts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/lists/{list_id}/companies", status_code=status.HTTP_200_OK)
async def add_companies_to_list(
    list_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    company_ids = body.get("company_ids", [])
    if not company_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_ids required")
    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    result = await session.execute(select(Company).where(Company.id.in_(company_ids)))
    companies = list(result.scalars().unique().all())
    added = 0
    for company in companies:
        exists = await session.execute(
            select(ListCompany).where(ListCompany.list_id == list_id, ListCompany.company_id == company.id)
        )
        if not exists.scalar_one_or_none():
            session.add(ListCompany(list_id=list_id, company_id=company.id))
            added += 1
    await session.commit()
    return {"added": added, "total": len(companies)}


@router.delete("/lists/{list_id}/companies", status_code=status.HTTP_200_OK)
async def remove_companies_from_list(
    list_id: int,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    company_ids = body.get("company_ids", [])
    if not company_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_ids required")
    result = await session.execute(
        select(ListCompany).where(ListCompany.list_id == list_id, ListCompany.company_id.in_(company_ids))
    )
    rows = list(result.scalars().all())
    for row in rows:
        await session.delete(row)
    await session.commit()
    return {"removed": len(rows)}
