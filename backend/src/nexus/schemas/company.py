from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyBase(BaseModel):
    name: str = Field(..., max_length=300)
    website: str | None = Field(None, max_length=500)
    domain: str | None = Field(None, max_length=255)
    linkedin_url: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=200)
    sub_industry: str | None = Field(None, max_length=200)
    employee_count: int | None = None
    company_size: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    headquarters: str | None = Field(None, max_length=200)
    founded_year: int | None = None
    technologies: list[str] = Field(default_factory=list)
    funding_stage: str | None = Field(None, max_length=100)
    company_status: str | None = Field(None, max_length=100)
    source: str | None = Field(None, max_length=200)
    notes: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(None, max_length=300)
    website: str | None = Field(None, max_length=500)
    domain: str | None = Field(None, max_length=255)
    linkedin_url: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=200)
    sub_industry: str | None = Field(None, max_length=200)
    employee_count: int | None = None
    company_size: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    headquarters: str | None = Field(None, max_length=200)
    founded_year: int | None = None
    technologies: list[str] | None = None
    funding_stage: str | None = Field(None, max_length=100)
    company_status: str | None = Field(None, max_length=100)
    source: str | None = Field(None, max_length=200)
    notes: str | None = None
    tags: list[str] | None = None
    last_verified: datetime | None = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    website: str | None
    domain: str | None
    linkedin_url: str | None
    industry: str | None
    sub_industry: str | None
    employee_count: int | None
    company_size: str | None
    country: str | None
    state: str | None
    city: str | None
    headquarters: str | None
    founded_year: int | None
    technologies: list[str]
    funding_stage: str | None
    company_status: str | None
    source: str | None
    notes: str | None
    data_quality_score: int
    is_archived: bool
    last_verified: datetime | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    contact_count: int = 0
    tag_names: list[str] = Field(default_factory=list)


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int


class CompanyExportRow(BaseModel):
    company_name: str
    website: str | None
    domain: str | None
    linkedin_url: str | None
    industry: str | None
    sub_industry: str | None
    employee_count: int | None
    company_size: str | None
    country: str | None
    state: str | None
    city: str | None
    headquarters: str | None
    founded_year: int | None
    technologies: str
    funding_stage: str | None
    company_status: str | None
    source: str | None
    notes: str | None
    data_quality_score: int
    last_verified: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_db(cls, company: Any) -> CompanyExportRow:
        technologies = ", ".join(company.technologies or []) if company.technologies else ""
        last_verified = company.last_verified.isoformat() if company.last_verified else None
        return cls(
            company_name=company.name,
            website=company.website,
            domain=company.domain,
            linkedin_url=company.linkedin_url,
            industry=company.industry,
            sub_industry=company.sub_industry,
            employee_count=company.employee_count,
            company_size=company.company_size,
            country=company.country,
            state=company.state,
            city=company.city,
            headquarters=company.headquarters,
            founded_year=company.founded_year,
            technologies=technologies,
            funding_stage=company.funding_stage,
            company_status=company.company_status,
            source=company.source,
            notes=company.notes,
            data_quality_score=company.data_quality_score,
            last_verified=last_verified,
            created_at=company.created_at.isoformat() if company.created_at else None,
            updated_at=company.updated_at.isoformat() if company.updated_at else None,
        )
