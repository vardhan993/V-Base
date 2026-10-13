from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus.core.phones import normalize_phone
from nexus.database import CRM_STAGES
from nexus.schemas.company import CompanyResponse


def _coerce_list(v: Any) -> list:
    if v is None:
        return []
    return v


class ContactBase(BaseModel):
    first_name: str | None = Field(None, max_length=150)
    last_name: str | None = Field(None, max_length=150)
    full_name: str | None = Field(None, max_length=300)
    job_title: str | None = Field(None, max_length=300)
    department: str | None = Field(None, max_length=150)
    seniority: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=254)
    email_status: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=50)
    phone_status: str | None = Field(None, max_length=50)
    stage: str = Field("New", max_length=50)
    linkedin_url: str | None = Field(None, max_length=500)
    company_name: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    skills: list[str] = Field(default_factory=list)
    employment_history: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = Field(None, max_length=200)
    notes: str | None = None
    company_id: int | None = None

    @field_validator("skills", "employment_history", mode="before")
    @classmethod
    def _coerce_empty_lists(cls, v: Any) -> Any:
        return _coerce_list(v)

    @field_validator("stage", mode="before")
    @classmethod
    def _default_stage(cls, v: Any) -> Any:
        if v in (None, ""):
            return "New"
        if v not in CRM_STAGES:
            raise ValueError(f"stage must be one of: {', '.join(CRM_STAGES)}")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        parsed = normalize_phone(v)
        # Unparseable input is kept as typed (trimmed) so no user data is
        # destroyed; Data Quality flags it instead of the API rejecting it.
        return parsed.display if parsed else (v.strip() if isinstance(v, str) else v)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    first_name: str | None = Field(None, max_length=150)
    last_name: str | None = Field(None, max_length=150)
    full_name: str | None = Field(None, max_length=300)
    job_title: str | None = Field(None, max_length=300)
    department: str | None = Field(None, max_length=150)
    seniority: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=254)
    email_status: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=50)
    phone_status: str | None = Field(None, max_length=50)
    stage: str | None = Field(None, max_length=50)
    linkedin_url: str | None = Field(None, max_length=500)
    company_name: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    skills: list[str] | None = None
    employment_history: list[dict[str, Any]] | None = None
    source: str | None = Field(None, max_length=200)
    notes: str | None = None
    company_id: int | None = None
    tags: list[str] | None = None
    last_verified: datetime | None = None

    @field_validator("stage", mode="before")
    @classmethod
    def _check_stage(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        if v not in CRM_STAGES:
            raise ValueError(f"stage must be one of: {', '.join(CRM_STAGES)}")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        parsed = normalize_phone(v)
        return parsed.display if parsed else (v.strip() if isinstance(v, str) else v)


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str | None
    last_name: str | None
    full_name: str | None
    job_title: str | None
    department: str | None
    seniority: str | None
    email: str | None
    email_status: str | None
    phone: str | None
    phone_status: str | None
    stage: str
    linkedin_url: str | None
    company_name: str | None
    city: str | None
    country: str | None
    skills: list[str] = Field(default_factory=list)
    employment_history: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None
    notes: str | None
    data_quality_score: int
    is_archived: bool
    last_verified: datetime | None
    company_id: int | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    company: CompanyResponse | None = None
    tag_names: list[str] = Field(default_factory=list)
    display_name: str = ""

    @field_validator("skills", "employment_history", "tag_names", mode="before")
    @classmethod
    def _coerce_empty_lists(cls, v: Any) -> Any:
        return _coerce_list(v)


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    page: int
    page_size: int


class ContactExportRow(BaseModel):
    first_name: str | None
    last_name: str | None
    full_name: str | None
    job_title: str | None
    department: str | None
    seniority: str | None
    email: str | None
    email_status: str | None
    phone: str | None
    phone_status: str | None
    stage: str | None
    linkedin_url: str | None
    company_name: str | None
    city: str | None
    country: str | None
    skills: str
    employment_history: str
    source: str | None
    notes: str | None
    data_quality_score: int
    last_verified: str | None
    created_at: str
    updated_at: str
    company_name_resolved: str | None = None

    @classmethod
    def from_db(cls, contact: Any) -> ContactExportRow:
        skills = ", ".join(contact.skills or []) if contact.skills else ""
        employment_history = (
            "; ".join(
                f"{e.get('company_name') or ''}: {e.get('job_title') or ''} ({e.get('start_date') or ''} - {e.get('end_date') or ''})"
                for e in (contact.employment_history or [])
            )
            or ""
        )
        company_name_resolved = None
        if contact.company:
            company_name_resolved = contact.company.name
        last_verified = contact.last_verified.isoformat() if contact.last_verified else None
        return cls(
            first_name=contact.first_name,
            last_name=contact.last_name,
            full_name=contact.full_name,
            job_title=contact.job_title,
            department=contact.department,
            seniority=contact.seniority,
            email=contact.email,
            email_status=contact.email_status,
            phone=contact.phone,
            phone_status=contact.phone_status,
            stage=contact.stage,
            linkedin_url=contact.linkedin_url,
            company_name=contact.company_name,
            city=contact.city,
            country=contact.country,
            skills=skills,
            employment_history=employment_history,
            source=contact.source,
            notes=contact.notes,
            data_quality_score=contact.data_quality_score,
            last_verified=last_verified,
            created_at=contact.created_at.isoformat() if contact.created_at else None,
            updated_at=contact.updated_at.isoformat() if contact.updated_at else None,
            company_name_resolved=company_name_resolved,
        )
