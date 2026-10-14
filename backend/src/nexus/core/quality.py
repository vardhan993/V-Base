"""Data-quality scoring for contacts and companies.

One implementation, shared by the record endpoints and the lead-conversion
endpoint, so a converted record scores exactly like a hand-created one. The
formulas are intentionally simple and additive: each signal that is present
adds points, capped at 100.
"""

from __future__ import annotations

from typing import Any


def contact_quality(contact: Any) -> int:
    """Completeness score for a contact (0-100).

    Accepts either a :class:`~nexus.database.Contact` or a
    :class:`~nexus.schemas.contact.ContactCreate`; the verified-recency bonus
    only applies to a persisted row, which carries ``last_verified``.
    """
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
    last_verified = getattr(contact, "last_verified", None)
    if last_verified is not None:
        score += 10
    return min(100, score)


def company_quality(company: Any, *, contact_count: int | None = None) -> int:
    """Completeness score for a company (0-100).

    ``contact_count`` is how many contacts the company has. Pass it when the
    caller already knows the number (the conversion flow does). When omitted the
    loaded relationship is used if it happens to be loaded, and a fresh or
    schema object simply scores without that component — reading an unloaded
    relationship would trigger an implicit lazy load that async SQLAlchemy
    cannot perform.
    """
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
    if contact_count is None:
        contact_count = _loaded_contact_count(company)
    if contact_count:
        score += min(15, contact_count * 3)
    return min(100, score)


def _loaded_contact_count(company: Any) -> int:
    """Length of the already-loaded ``contacts`` collection, else 0."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm.attributes import NO_VALUE

    try:
        state = sa_inspect(company)
    except Exception:  # not a mapped instance (e.g. a Pydantic schema object)
        return 0
    try:
        loaded = state.attrs.contacts.loaded_value
    except (AttributeError, KeyError):
        return 0
    if loaded is NO_VALUE or loaded is None:
        return 0
    try:
        return len(loaded)
    except TypeError:
        return 0


__all__ = ["company_quality", "contact_quality"]
