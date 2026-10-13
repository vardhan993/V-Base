from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity, record_audit, snapshot
from nexus.core.counts import attach_contact_counts_for_company
from nexus.core.db import get_session
from nexus.database import Company, Contact, ContactTag, Tag
from nexus.schemas.company import CompanyResponse
from nexus.schemas.contact import (
    ContactCreate,
    ContactExportRow,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)

router = APIRouter(tags=["contacts"])

#: Columns captured in audit before/after payloads.
_AUDIT_FIELDS = [
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
    "company_id",
    "city",
    "country",
    "data_quality_score",
    "is_archived",
]


@router.get("/contacts", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str = Query("", max_length=500),
    name: str = Query("", max_length=300),
    job_title: str = Query("", max_length=300),
    company_name: str = Query("", max_length=300),
    email: str = Query("", max_length=254),
    phone: str = Query("", max_length=50),
    city: str = Query("", max_length=100),
    country: str = Query("", max_length=100),
    email_status: str | None = Query(None, max_length=50),
    phone_status: str | None = Query(None, max_length=50),
    linkedin_available: bool | None = Query(None),
    email_available: bool | None = Query(None),
    phone_available: bool | None = Query(None),
    seniority: str | None = Query(None, max_length=100),
    department: str | None = Query(None, max_length=150),
    data_quality_min: int | None = Query(None, ge=0, le=100),
    data_quality_max: int | None = Query(None, ge=0, le=100),
    tags: str = Query("", max_length=500),
    sort: str = Query("updated_at"),
    order: str = Query("desc"),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Contact).where(
        Contact.is_archived.is_(False) if archived is None else Contact.is_archived == archived
    )

    if q:
        base = base.where(Contact.search_filter(q))
    if name:
        base = base.where(
            (Contact.full_name.ilike(f"%{name}%"))
            | (Contact.first_name.ilike(f"%{name}%"))
            | (Contact.last_name.ilike(f"%{name}%"))
        )
    if job_title:
        base = base.where(Contact.job_title.ilike(f"%{job_title}%"))
    if company_name:
        base = base.where(Contact.company_name.ilike(f"%{company_name}%"))
    if email:
        base = base.where(Contact.email.ilike(f"%{email}%"))
    if phone:
        base = base.where(Contact.phone.ilike(f"%{phone}%"))
    if city:
        base = base.where(Contact.city.ilike(f"%{city}%"))
    if country:
        base = base.where(Contact.country.ilike(f"%{country}%"))
    if email_status:
        base = base.where(Contact.email_status == email_status)
    if phone_status:
        base = base.where(Contact.phone_status == phone_status)
    if linkedin_available is True:
        base = base.where(Contact.linkedin_url.isnot(None))
    elif linkedin_available is False:
        base = base.where(Contact.linkedin_url.is_(None))
    if email_available is True:
        base = base.where(Contact.email.isnot(None))
    elif email_available is False:
        base = base.where(Contact.email.is_(None))
    if phone_available is True:
        base = base.where(Contact.phone.isnot(None))
    elif phone_available is False:
        base = base.where(Contact.phone.is_(None))
    if seniority:
        base = base.where(Contact.seniority.ilike(f"%{seniority}%"))
    if department:
        base = base.where(Contact.department.ilike(f"%{department}%"))
    if data_quality_min is not None:
        base = base.where(Contact.data_quality_score >= data_quality_min)
    if data_quality_max is not None:
        base = base.where(Contact.data_quality_score <= data_quality_max)

    if tags:
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_names:
            tag_stmt = select(Tag.id).where(Tag.name.in_(tag_names))
            tag_result = await session.execute(tag_stmt)
            tag_ids = [r[0] for r in tag_result.fetchall()]
            if tag_ids:
                ct_stmt = select(ContactTag.contact_id).where(ContactTag.tag_id.in_(tag_ids))
                ct_result = await session.execute(ct_stmt)
                contact_ids = {r[0] for r in ct_result.fetchall()}
                base = base.where(Contact.id.in_(list(contact_ids)))

    sort_col = _contact_sort_column(sort)
    base = base.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    count_stmt = select(func.count()).select_from(base.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    base = base.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(base)
    contacts = list(result.scalars().unique().all())

    items = []
    for contact in contacts:
        resp = ContactResponse.model_validate(contact)
        resp.display_name = contact.display_name
        items.append(resp)

    return ContactListResponse(items=items, total=total, page=page, page_size=page_size)


def _contact_sort_column(sort: str):
    mapping = {
        "updated_at": Contact.updated_at,
        "created_at": Contact.created_at,
        "full_name": Contact.full_name,
        "job_title": Contact.job_title,
        "email": Contact.email,
        "phone": Contact.phone,
        "city": Contact.city,
        "data_quality_score": Contact.data_quality_score,
    }
    return mapping.get(sort, Contact.updated_at)


# NOTE: /contacts/export must be registered before /contacts/{contact_id},
# otherwise FastAPI matches "export" against the integer path parameter.
@router.get("/contacts/export")
async def export_contacts(
    q: str = Query("", max_length=500),
    job_title: str = Query("", max_length=300),
    company_name: str = Query("", max_length=300),
    city: str = Query("", max_length=100),
    country: str = Query("", max_length=100),
    email_status: str | None = Query(None),
    seniority: str | None = Query(None),
    archived: bool | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Contact).where(
        Contact.is_archived.is_(False) if archived is None else Contact.is_archived == archived
    )
    if q:
        base = base.where(Contact.search_filter(q))
    if job_title:
        base = base.where(Contact.job_title.ilike(f"%{job_title}%"))
    if company_name:
        base = base.where(Contact.company_name.ilike(f"%{company_name}%"))
    if city:
        base = base.where(Contact.city.ilike(f"%{city}%"))
    if country:
        base = base.where(Contact.country.ilike(f"%{country}%"))
    if email_status:
        base = base.where(Contact.email_status == email_status)
    if seniority:
        base = base.where(Contact.seniority.ilike(f"%{seniority}%"))
    result = await session.execute(base.order_by(Contact.updated_at.desc()))
    contacts = list(result.scalars().unique().all())
    rows = [ContactExportRow.from_db(c) for c in contacts]
    return {"rows": [r.model_dump() for r in rows], "count": len(rows)}


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    company = None
    if body.company_name:
        stmt = select(Company).where(Company.name.ilike(body.company_name)).limit(1)
        result = await session.execute(stmt)
        company = result.scalar_one_or_none()
    contact = Contact(
        **body.model_dump(), company=company, created_by_id=current_user.id, data_quality_score=_contact_quality(body)
    )
    session.add(contact)
    await session.flush()
    if company:
        contact.company_id = company.id
        await session.flush()
    await record_activity(
        session,
        action="contact_created",
        user_id=current_user.id,
        entity_type="contacts",
        entity_id=contact.id,
        description=f"Created contact {contact.display_name or contact.email or contact.id}",
        metadata={"email": contact.email, "company": contact.company_name},
    )
    await record_audit(
        session,
        action="create",
        entity_type="contact",
        entity_id=contact.id,
        user_id=current_user.id,
        after=snapshot(contact, _AUDIT_FIELDS),
    )
    await session.commit()
    await session.refresh(contact)
    resp = ContactResponse.model_validate(contact)
    resp.display_name = contact.display_name
    return resp


@router.get("/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    resp = ContactResponse.model_validate(contact)
    resp.display_name = contact.display_name
    return resp


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    body: ContactUpdate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    update_data = body.model_dump(exclude_unset=True)
    before = snapshot(contact, _AUDIT_FIELDS)
    company = None
    if "company_name" in update_data and update_data["company_name"]:
        stmt = select(Company).where(Company.name.ilike(update_data["company_name"])).limit(1)
        result = await session.execute(stmt)
        company = result.scalar_one_or_none()
    if "tags" in update_data:
        incoming = set()
        for tag_name in update_data["tags"]:
            tag = await _get_or_create_tag(session, tag_name)
            incoming.add(tag.id)
            if tag not in contact.tags:
                contact.tags.append(tag)
        contact.tags = [t for t in contact.tags if t.id in incoming]
    for key, value in update_data.items():
        if key == "tags":
            continue
        setattr(contact, key, value)
    if company:
        await attach_contact_counts_for_company(session, company)
        contact.company = company
        contact.company_id = company.id
    elif "company_name" in update_data and not update_data["company_name"]:
        contact.company = None
        contact.company_id = None
    contact.data_quality_score = _contact_quality(contact)
    await session.flush()
    changed = _diff_fields(before, snapshot(contact, _AUDIT_FIELDS))
    if changed:
        await record_activity(
            session,
            action="contact_updated",
            user_id=current_user.id,
            entity_type="contacts",
            entity_id=contact.id,
            description=f"Updated {len(changed)} field(s) on {contact.display_name or contact.email}",
            metadata={"changed": sorted(changed)},
        )
        await record_audit(
            session,
            action="update",
            entity_type="contact",
            entity_id=contact.id,
            user_id=current_user.id,
            before=before,
            after=snapshot(contact, _AUDIT_FIELDS),
        )
    await session.commit()
    await session.refresh(contact)
    resp = ContactResponse.model_validate(contact)
    resp.display_name = contact.display_name
    return resp


@router.get("/contacts/{contact_id}/company", response_model=CompanyResponse | None)
async def get_contact_company(
    contact_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if not contact.company_id:
        return None
    company = await session.get(Company, contact.company_id)
    if not company:
        return None
    await attach_contact_counts_for_company(session, company)
    return CompanyResponse.model_validate(company)


@router.post("/contacts/{contact_id}/archive", response_model=ContactResponse)
async def archive_contact(
    contact_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    contact.is_archived = True
    await record_activity(
        session,
        action="contact_archived",
        user_id=current_user.id,
        entity_type="contacts",
        entity_id=contact.id,
        description=f"Archived contact {contact.display_name or contact.email}",
    )
    await session.commit()
    await session.refresh(contact)
    resp = ContactResponse.model_validate(contact)
    resp.display_name = contact.display_name
    return resp


@router.post("/contacts/{contact_id}/restore", response_model=ContactResponse)
async def restore_contact(
    contact_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    contact.is_archived = False
    await record_activity(
        session,
        action="contact_restored",
        user_id=current_user.id,
        entity_type="contacts",
        entity_id=contact.id,
        description=f"Restored contact {contact.display_name or contact.email}",
    )
    await session.commit()
    await session.refresh(contact)
    resp = ContactResponse.model_validate(contact)
    resp.display_name = contact.display_name
    return resp


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int, session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact = await session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await record_audit(
        session,
        action="delete",
        entity_type="contact",
        entity_id=contact.id,
        user_id=current_user.id,
        before=snapshot(contact, _AUDIT_FIELDS),
    )
    await session.delete(contact)
    await session.commit()


@router.post("/contacts/bulk-tag", status_code=status.HTTP_200_OK)
async def bulk_tag_contacts(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact_ids = body.get("contact_ids", [])
    tag_names = body.get("tags", [])
    if not contact_ids or not tag_names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_ids and tags required")
    result = await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))
    contacts = list(result.scalars().unique().all())
    for tag_name in tag_names:
        tag = await _get_or_create_tag(session, tag_name)
        for contact in contacts:
            if tag not in contact.tags:
                contact.tags.append(tag)
    await session.commit()
    return {"updated": len(contacts), "tags": tag_names}


@router.post("/contacts/bulk-list", status_code=status.HTTP_200_OK)
async def bulk_list_contacts(
    body: dict[str, Any], session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)
):
    contact_ids = body.get("contact_ids", [])
    list_id = body.get("list_id")
    if not contact_ids or not list_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_ids and list_id required")
    from nexus.database import ContactList, ListContact

    list_obj = await session.get(ContactList, list_id)
    if not list_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    result = await session.execute(select(Contact).where(Contact.id.in_(contact_ids)))
    contacts = list(result.scalars().unique().all())
    for contact in contacts:
        exists = await session.execute(
            select(ListContact).where(ListContact.list_id == list_id, ListContact.contact_id == contact.id)
        )
        if not exists.scalar_one_or_none():
            session.add(ListContact(list_id=list_id, contact_id=contact.id))
    await session.commit()
    return {"updated": len(contacts)}


async def _get_or_create_tag(session: AsyncSession, name: str) -> Tag:
    from nexus.database import Tag

    stmt = select(Tag).where(Tag.name == name)
    result = await session.execute(stmt)
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name, kind="contact")
        session.add(tag)
        await session.flush()
    return tag


def _diff_fields(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """Field names whose value changed between two audit snapshots."""
    return {key for key in after if before.get(key) != after.get(key)}


def _contact_quality(contact: Contact | ContactCreate) -> int:
    score = 0
    if contact.full_name or contact.first_name or contact.last_name:
        score += 10
    if contact.email:
        score += 25
    if contact.phone:
        score += 20
    if contact.linkedin_url:
        score += 20
    if contact.company_id or contact.company_name:
        score += 15
    if contact.job_title:
        score += 10
    if isinstance(contact, Contact):
        if contact.last_verified:
            score += 10
    return min(100, score)
