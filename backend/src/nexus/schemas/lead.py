from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus.core.lead_scoring import summarise
from nexus.core.phones import normalize_phone
from nexus.database import LEAD_PRIORITIES, LEAD_STAGES, LEAD_STATUSES
from nexus.schemas.company import CompanyResponse
from nexus.schemas.contact import ContactResponse


def _coerce_list(v: Any) -> list:
    if v is None:
        return []
    return v


def _validate_choice(value: Any, allowed: tuple[str, ...], field: str) -> Any:
    if value in (None, ""):
        return value
    if value not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(allowed)}")
    return value


class LeadBase(BaseModel):
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
    linkedin_url: str | None = Field(None, max_length=500)
    website: str | None = Field(None, max_length=500)
    company_name: str | None = Field(None, max_length=300)
    company_domain: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=200)
    employee_count: int | None = Field(None, ge=0)
    company_size: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    lead_source: str | None = Field(None, max_length=200)
    campaign: str | None = Field(None, max_length=200)
    lifecycle_stage: str = Field("New", max_length=50)
    lead_status: str = Field("New", max_length=50)
    priority: str = Field("Medium", max_length=20)
    owner_id: int | None = None
    company_id: int | None = None
    next_follow_up_at: datetime | None = None
    consent_status: str | None = Field(None, max_length=50)
    do_not_contact: bool = False
    disqualified_reason: str | None = Field(None, max_length=300)
    notes: str | None = None
    last_verified: datetime | None = None

    @field_validator("lifecycle_stage", mode="before")
    @classmethod
    def _check_stage(cls, v: Any) -> Any:
        if v in (None, ""):
            return "New"
        return _validate_choice(v, LEAD_STAGES, "lifecycle_stage")

    @field_validator("lead_status", mode="before")
    @classmethod
    def _check_status(cls, v: Any) -> Any:
        if v in (None, ""):
            return "New"
        unless_converted = tuple(s for s in LEAD_STATUSES if s != "Converted")
        if v == "Converted":
            # Only the conversion endpoint may set this, so a create/update
            # payload cannot fake a conversion.
            raise ValueError("lead_status 'Converted' is set by the convert endpoint, not directly")
        return _validate_choice(v, unless_converted, "lead_status")

    @field_validator("priority", mode="before")
    @classmethod
    def _check_priority(cls, v: Any) -> Any:
        if v in (None, ""):
            return "Medium"
        return _validate_choice(v, LEAD_PRIORITIES, "priority")

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        parsed = normalize_phone(v)
        # Unparseable input is kept as typed (trimmed) so no user data is
        # destroyed; Data Quality flags it rather than the API rejecting it.
        return parsed.display if parsed else (v.strip() if isinstance(v, str) else v)


class LeadCreate(LeadBase):
    tags: list[str] | None = None


class LeadUpdate(BaseModel):
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
    linkedin_url: str | None = Field(None, max_length=500)
    website: str | None = Field(None, max_length=500)
    company_name: str | None = Field(None, max_length=300)
    company_domain: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=200)
    employee_count: int | None = Field(None, ge=0)
    company_size: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    lead_source: str | None = Field(None, max_length=200)
    campaign: str | None = Field(None, max_length=200)
    lifecycle_stage: str | None = Field(None, max_length=50)
    lead_status: str | None = Field(None, max_length=50)
    priority: str | None = Field(None, max_length=20)
    owner_id: int | None = None
    company_id: int | None = None
    next_follow_up_at: datetime | None = None
    consent_status: str | None = Field(None, max_length=50)
    do_not_contact: bool | None = None
    disqualified_reason: str | None = Field(None, max_length=300)
    notes: str | None = None
    last_verified: datetime | None = None
    tags: list[str] | None = None
    #: Explicit opt-in to re-run scoring when the record changes. Scoring also
    #: runs automatically on create and on any change to a scored field.
    rescore: bool | None = None

    @field_validator("lifecycle_stage", mode="before")
    @classmethod
    def _check_stage(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        return _validate_choice(v, LEAD_STAGES, "lifecycle_stage")

    @field_validator("lead_status", mode="before")
    @classmethod
    def _check_status(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        if v == "Converted":
            raise ValueError("lead_status 'Converted' is set by the convert endpoint, not directly")
        return _validate_choice(v, tuple(s for s in LEAD_STATUSES if s != "Converted"), "lead_status")

    @field_validator("priority", mode="before")
    @classmethod
    def _check_priority(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        return _validate_choice(v, LEAD_PRIORITIES, "priority")

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Any:
        if v in (None, ""):
            return v
        parsed = normalize_phone(v)
        return parsed.display if parsed else (v.strip() if isinstance(v, str) else v)


class ScoreRule(BaseModel):
    key: str
    label: str
    kind: str
    weight: int
    points: int
    earned: bool
    detail: str


class LeadResponse(BaseModel):
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
    linkedin_url: str | None
    website: str | None
    company_name: str | None
    company_domain: str | None
    industry: str | None
    employee_count: int | None
    company_size: str | None
    city: str | None
    state: str | None
    country: str | None
    lead_source: str | None
    campaign: str | None
    lifecycle_stage: str
    lead_status: str
    priority: str
    lead_score: int
    score_breakdown: list[ScoreRule] = Field(default_factory=list)
    score_updated_at: datetime | None
    owner_id: int | None
    company_id: int | None
    next_follow_up_at: datetime | None
    consent_status: str | None
    do_not_contact: bool
    disqualified_reason: str | None
    notes: str | None
    converted_contact_id: int | None
    converted_company_id: int | None
    converted_at: datetime | None
    data_quality_score: int
    is_archived: bool
    last_verified: datetime | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    tag_names: list[str] = Field(default_factory=list)
    display_name: str = ""
    #: Derived from the stored breakdown so the UI can show the split without
    #: recomputing it; filled in by the API layer.
    fit_score: int = 0
    engagement_score: int = 0
    score_summary: str = ""

    @field_validator("score_breakdown", "tag_names", mode="before")
    @classmethod
    def _coerce_empty_lists(cls, v: Any) -> Any:
        return _coerce_list(v)


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    page_size: int


class LeadExportRow(BaseModel):
    full_name: str | None
    job_title: str | None
    email: str | None
    email_status: str | None
    phone: str | None
    phone_status: str | None
    linkedin_url: str | None
    company_name: str | None
    company_domain: str | None
    industry: str | None
    employee_count: int | None
    company_size: str | None
    city: str | None
    state: str | None
    country: str | None
    lead_source: str | None
    campaign: str | None
    lifecycle_stage: str
    lead_status: str
    priority: str
    lead_score: int
    score_summary: str
    next_follow_up_at: str | None
    consent_status: str | None
    do_not_contact: bool
    disqualified_reason: str | None
    notes: str | None
    tags: str
    data_quality_score: int
    converted_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_db(cls, lead: Any) -> LeadExportRow:
        breakdown = _coerce_list(getattr(lead, "score_breakdown", None))
        return cls(
            full_name=lead.display_name or None,
            job_title=lead.job_title,
            email=lead.email,
            email_status=lead.email_status,
            phone=lead.phone,
            phone_status=lead.phone_status,
            linkedin_url=lead.linkedin_url,
            company_name=lead.company_name,
            company_domain=lead.company_domain,
            industry=lead.industry,
            employee_count=lead.employee_count,
            company_size=lead.company_size,
            city=lead.city,
            state=lead.state,
            country=lead.country,
            lead_source=lead.lead_source,
            campaign=lead.campaign,
            lifecycle_stage=lead.lifecycle_stage,
            lead_status=lead.lead_status,
            priority=lead.priority,
            lead_score=lead.lead_score,
            score_summary=summarise(breakdown),
            next_follow_up_at=lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None,
            consent_status=lead.consent_status,
            do_not_contact=lead.do_not_contact,
            disqualified_reason=lead.disqualified_reason,
            notes=lead.notes,
            tags=", ".join(t.name for t in (lead.tags or [])),
            data_quality_score=lead.data_quality_score,
            converted_at=lead.converted_at.isoformat() if lead.converted_at else None,
            created_at=lead.created_at.isoformat() if lead.created_at else None,
            updated_at=lead.updated_at.isoformat() if lead.updated_at else None,
        )


class LeadConvertRequest(BaseModel):
    """Conversion instructions.

    The caller chooses, per side, whether to match an existing record or create
    a new one. Matching is by id (explicit) or by email/domain (automatic) so a
    conversion can never silently invent a duplicate contact or company.
    """

    company_mode: Literal["auto", "create", "link", "none"] = "auto"
    company_id: int | None = None
    contact_mode: Literal["auto", "create", "link"] = "auto"
    contact_id: int | None = None
    #: Stage for the created/linked contact; defaults to "New".
    contact_stage: str | None = None
    #: Copy lead values into blank contact/company fields (never overwrites).
    fill_missing_fields: bool = True
    #: Free-text note appended to the created record's notes.
    note: str | None = Field(None, max_length=2000)


class LeadConvertResponse(BaseModel):
    lead: LeadResponse
    contact: ContactResponse
    company: CompanyResponse | None = None
    created_contact: bool
    created_company: bool


__all__ = [
    "LeadBase",
    "LeadConvertRequest",
    "LeadConvertResponse",
    "LeadCreate",
    "LeadExportRow",
    "LeadListResponse",
    "LeadResponse",
    "LeadUpdate",
    "ScoreRule",
]
