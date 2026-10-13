from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Company, CompanyTag, Contact, ContactTag, Tag

router = APIRouter(tags=["tags"])


@router.get("/tags")
async def list_tags(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    stmt = select(Tag).order_by(Tag.name)
    result = await session.execute(stmt)
    tags = list(result.scalars().unique().all())
    return [
        {
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "kind": t.kind,
            "contact_count": len(t.contacts),
            "company_count": len(t.companies),
        }
        for t in tags
    ]


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: dict[str, str], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    # Tag names are globally unique; check first so the caller gets a 409
    # instead of an IntegrityError surfacing as a 500.
    existing = (await session.execute(select(Tag).where(func.lower(Tag.name) == name.lower()))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tag '{existing.name}' already exists")

    tag = Tag(name=name, color=body.get("color"), kind=body.get("kind"), created_by_id=current_user.id)
    session.add(tag)
    await session.flush()
    await session.refresh(tag)
    await session.commit()
    return {"id": tag.id, "name": tag.name, "color": tag.color, "kind": tag.kind}


@router.patch("/tags/{tag_id}", status_code=status.HTTP_200_OK)
async def update_tag(
    tag_id: int,
    body: dict[str, str],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be blank")
        clash = (
            await session.execute(select(Tag).where(func.lower(Tag.name) == new_name.lower(), Tag.id != tag_id))
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tag '{clash.name}' already exists")
        tag.name = new_name
    if "color" in body:
        tag.color = body["color"]
    if "kind" in body:
        tag.kind = body["kind"]
    await session.commit()
    await session.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color, "kind": tag.kind}


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    await session.delete(tag)
    await session.commit()


@router.post("/tags/bulk-apply", status_code=status.HTTP_200_OK)
async def bulk_apply_tag(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    tag_id = body.get("tag_id")
    contact_ids = body.get("contact_ids", [])
    company_ids = body.get("company_ids", [])
    if not tag_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tag_id required")

    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    if contact_ids:
        contacts = (await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().unique().all()
        for contact in contacts:
            if tag not in contact.tags:
                contact.tags.append(tag)
    if company_ids:
        companies = (await session.execute(select(Company).where(Company.id.in_(company_ids)))).scalars().unique().all()
        for company in companies:
            if tag not in company.tags:
                company.tags.append(tag)
    await session.commit()
    return {"contact_ids": len(contact_ids), "company_ids": len(company_ids)}


@router.post("/tags/bulk-remove", status_code=status.HTTP_200_OK)
async def bulk_remove_tag(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    tag_id = body.get("tag_id")
    contact_ids = body.get("contact_ids", [])
    company_ids = body.get("company_ids", [])
    if not tag_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tag_id required")

    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    if contact_ids:
        result = await session.execute(
            select(ContactTag).where(ContactTag.tag_id == tag_id, ContactTag.contact_id.in_(contact_ids))
        )
        for ct in result.scalars().all():
            await session.delete(ct)
    if company_ids:
        result = await session.execute(
            select(CompanyTag).where(CompanyTag.tag_id == tag_id, CompanyTag.company_id.in_(company_ids))
        )
        for ct in result.scalars().all():
            await session.delete(ct)
    await session.commit()
    return {"contact_ids": len(contact_ids), "company_ids": len(company_ids)}
