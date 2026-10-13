"""Derived counts attached to ORM instances before they are serialised.

These values are computed with one grouped query per request rather than read
from a relationship. Reading ``company.contacts`` would trigger a lazy load:
async SQLAlchemy cannot do that implicitly, so it raises ``MissingGreenlet``
unless the relationship happened to be eager-loaded by the query that fetched
the row. A grouped aggregate is also cheaper than loading every related row just
to count it.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database.models import Company, Contact


async def attach_contact_counts(session: AsyncSession, companies: Sequence[Company]) -> None:
    """Set ``contact_count`` on each company: non-archived contacts only.

    Archiving a contact deliberately removes it from the count without
    destroying the link, so the number always matches what the Contacts list
    shows for that company.
    """
    ids = [company.id for company in companies if company is not None]
    if not ids:
        return

    rows = await session.execute(
        select(Contact.company_id, func.count(Contact.id))
        .where(Contact.company_id.in_(ids), Contact.is_archived.is_(False))
        .group_by(Contact.company_id)
    )
    counts = {company_id: count for company_id, count in rows.all()}
    for company in companies:
        if company is not None:
            company.contact_count = counts.get(company.id, 0)


async def attach_contact_counts_for_company(session: AsyncSession, company: Company | None) -> None:
    """Single-company convenience wrapper used by the detail routes."""
    if company is not None:
        await attach_contact_counts(session, [company])
