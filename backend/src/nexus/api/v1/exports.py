from __future__ import annotations

import csv
import io
import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.db import get_session
from nexus.database import Company, Contact, ContactEmail, ContactPhone

router = APIRouter(tags=["exports"])

_VCARD_ESCAPE = {
    "\\": "\\\\",
    "\n": "\\n",
    ",": "\\,",
    ";": "\\;",
}


def _vcard_escape(value: str) -> str:
    for old, new in _VCARD_ESCAPE.items():
        value = value.replace(old, new)
    return value


def _stamp() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")


#: Cells starting with these characters are interpreted as formulas by Excel,
#: LibreOffice and Google Sheets when a CSV/XLSX is opened. A contact whose
#: name is ``=HYPERLINK(...)`` would otherwise execute in the recipient's
#: spreadsheet — the classic CSV injection. Prefixing with a single quote is
#: the standard neutralization.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _contact_row(contact: Contact, email: str | None, phone: str | None) -> dict[str, Any]:
    return {
        "id": contact.id,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "full_name": contact.display_name,
        "email": email or "",
        "email_status": contact.email_status or "",
        "phone": phone or "",
        "job_title": contact.job_title or "",
        "company_name": contact.company.name if contact.company else "",
        "city": contact.city or "",
        "country": contact.country or "",
        "linkedin_url": contact.linkedin_url or "",
        "stage": contact.stage or "",
        "seniority": contact.seniority or "",
        "department": contact.department or "",
    }


def _company_row(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "domain": company.domain or "",
        "industry": company.industry or "",
        "company_size": company.company_size or "",
        "employee_count": company.employee_count if company.employee_count is not None else "",
        "city": company.city or "",
        "country": company.country or "",
        "website": company.website or "",
    }


async def _load_contacts(session: AsyncSession, ids: list[int]) -> list[tuple[Contact, str | None, str | None]]:
    if not ids:
        raise ValueError("Provide contact_ids")
    rows = (await session.execute(select(Contact).where(Contact.id.in_(ids)))).scalars().all()
    emails: dict[int, str] = {}
    phones: dict[int, str] = {}
    if rows:
        id_list = [c.id for c in rows]
        for ce in (await session.execute(
            select(ContactEmail).where(ContactEmail.contact_id.in_(id_list), ContactEmail.is_primary.is_(True))
        )).scalars():
            emails[ce.contact_id] = ce.email
        for cp in (await session.execute(
            select(ContactPhone).where(ContactPhone.contact_id.in_(id_list), ContactPhone.is_primary.is_(True))
        )).scalars():
            phones[cp.contact_id] = cp.phone
    return [(c, emails.get(c.id), phones.get(c.id)) for c in rows]


def _csv_response(columns: list[str], rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _safe_cell(row.get(k, "")) for k in columns})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Exports contain sensitive CRM records; no cache may retain them.
            "Cache-Control": "no-store",
        },
    )


def _xlsx_response(columns: list[str], rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "export"
    ws.append(columns)
    for row in rows:
        ws.append([_safe_cell(row.get(c, "")) for c in columns])
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/exports/contacts")
async def export_contacts(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    ids: str = Query("", max_length=5000),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Export contacts by explicit ids (the SPA sends the current grid's
    selection or filtered id list). An id list keeps the endpoint decoupled
    from the query DSL and automatically honors whatever the user filtered."""
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list or len(id_list) > 5000:
        raise ValueError("Provide a comma-separated ids list (max 5000)")
    pairs = await _load_contacts(session, id_list)
    rows = [_contact_row(c, e, p) for c, e, p in pairs]
    columns = list(rows[0].keys()) if rows else ["id"]
    filename = f"contacts_{_stamp()}.{format}"
    if format == "xlsx":
        return _xlsx_response(columns, rows, filename)
    return _csv_response(columns, rows, filename)


@router.get("/exports/companies")
async def export_companies(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    ids: str = Query("", max_length=5000),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list or len(id_list) > 5000:
        raise ValueError("Provide a comma-separated ids list (max 5000)")
    rows = [_company_row(c) for c in (await session.execute(select(Company).where(Company.id.in_(id_list)))).scalars()]
    columns = list(rows[0].keys()) if rows else ["id"]
    filename = f"companies_{_stamp()}.{format}"
    if format == "xlsx":
        return _xlsx_response(columns, rows, filename)
    return _csv_response(columns, rows, filename)


@router.get("/contacts/{contact_id}/vcard")
async def contact_vcard(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise ValueError("Contact not found")

    rows = (await session.execute(
        select(ContactEmail).where(ContactEmail.contact_id == contact.id).order_by(ContactEmail.is_primary.desc())
    )).scalars().all()
    phones = (await session.execute(
        select(ContactPhone).where(ContactPhone.contact_id == contact.id).order_by(ContactPhone.is_primary.desc())
    )).scalars().all()

    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    name_parts = [part for part in (contact.first_name, contact.last_name) if part]
    if name_parts:
        lines.append(f"N:{_vcard_escape(contact.last_name or '')};{_vcard_escape(contact.first_name or '')};;;")
        lines.append(f"FN:{_vcard_escape(contact.display_name)}")
    elif contact.display_name:
        lines.append(f"FN:{_vcard_escape(contact.display_name)}")
    if contact.job_title:
        lines.append(f"TITLE:{_vcard_escape(contact.job_title)}")
    if contact.company is not None:
        lines.append(f"ORG:{_vcard_escape(contact.company.name)}")
    for ce in rows:
        lines.append(f"EMAIL;TYPE=INTERNET:{_vcard_escape(ce.email)}")
    for cp in phones:
        lines.append(f"TEL;TYPE=CELL:{_vcard_escape(cp.phone)}")
    if contact.linkedin_url:
        lines.append(f"URL:{_vcard_escape(contact.linkedin_url)}")
    lines.append(f"NOTE:{_vcard_escape(f'Imported into V-Base CRM — contact #{contact.id}')}")
    lines.append("END:VCARD")

    payload = "\r\n".join(lines) + "\r\n"
    return StreamingResponse(
        iter([payload]),
        media_type="text/vcard",
        headers={
            "Content-Disposition": f'attachment; filename="contact_{contact_id}.vcf"',
            "Content-Length": str(len(payload)),
        },
    )
