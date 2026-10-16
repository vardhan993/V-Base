from __future__ import annotations

import datetime
import re
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    or_,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.common.orm.orm.modelbase import Base

# ---------------------------------------------------------------------------
# Shared column helpers
# ---------------------------------------------------------------------------

#: JSONB is used throughout instead of plain JSON so the values are indexable
#: and the database enforces that only valid JSON is stored. ``default=dict``
#: covers ORM inserts while ``server_default`` covers raw SQL and dumps.
_JSONB_OBJECT = JSONB(astext_type=Text())


def _json_object_column(nullable: bool = False, **kwargs: Any):
    return mapped_column(
        JSONB,
        nullable=nullable,
        default=dict,
        server_default=text("'{}'::jsonb"),
        **kwargs,
    )


def _json_array_column(nullable: bool = False, **kwargs: Any):
    """An ordered JSONB list (webhook events, for example)."""
    return mapped_column(
        JSONB,
        nullable=nullable,
        default=list,
        server_default=text("'[]'::jsonb"),
        **kwargs,
    )


def _json_list_column(**kwargs: Any):
    return mapped_column(
        JSONB,
        nullable=True,
        default=list,
        server_default=text("'[]'::jsonb"),
        **kwargs,
    )


def _created_at_column():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated_at_column():
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


def _trgm_index(name: str, column: str, table: str) -> Index:
    """GIN trigram index over ``lower(column)``.

    The expression index is declared with raw SQL because SQLAlchemy drops
    ``postgresql_ops`` for functional index expressions, which would leave a
    GIN index with no operator class (and therefore no usable index). Declaring
    it explicitly keeps both the ``LIKE '%x%'`` and ``%`` search branches
    index-accelerated.
    """
    return Index(name, text(f"lower({column}) gin_trgm_ops"), postgresql_using="gin")


def _tsvector_expr(parts: str) -> str:
    """Build an IMMUTABLE expression for a stored ``tsvector`` column.

    PostgreSQL only accepts immutable expressions in GENERATED columns, so the
    config is cast to ``regconfig`` explicitly (the two-argument
    ``to_tsvector`` overload that resolves a config name at runtime is only
    STABLE) and NULLs are coalesced to the empty string.
    """
    return (
        "to_tsvector('english'::regconfig, "
        + " || ' ' || ".join(f"coalesce({part}, '')" for part in parts.split(", "))
        + ")"
    )


def build_search_condition(model: Any, query: str, trgm_columns: tuple[str, ...] = ()):
    """Return a SQLAlchemy condition searching ``model`` for ``query``.

    Three complementary strategies are OR-ed together, each backed by its own
    PostgreSQL index:

    1. Full-text search over the generated ``search_vector`` column (GIN), with
       prefix matching (``token:*``) so partial words match and stemming
       applies: ``analytic`` finds ``Analytics``.
    2. Trigram substring match via ``LIKE '%token%'`` on the identifying text
       columns, accelerated by the GIN ``gin_trgm_ops`` index. This catches
       matches inside a word (``wind`` finds ``Northwind``) where FTS
       tokenisation would not.
    3. Trigram similarity via the ``%`` operator (``pg_trgm.similarity_threshold``,
       default 0.3), accelerated by the same index, so misspellings of a whole
       value still match: ``Northwind Analytcs`` finds ``Northwind Analytics``.

    Every token is reduced to ``\\w+`` characters before it reaches SQL, so user
    input can never be injected as tsquery syntax.
    """
    tokens = re.findall(r"\w+", query or "")[:12]
    if not tokens:
        return false()

    lowered = [t.lower() for t in tokens]
    tsquery = " & ".join(f"{t}:*" for t in lowered)
    conditions = [model.search_vector.op("@@")(func.to_tsquery("english", tsquery))]

    for column_name in trgm_columns:
        column = getattr(model, column_name, None)
        if column is None:
            continue
        lowered_column = func.lower(column)
        for token in lowered[:6]:
            conditions.append(lowered_column.like(f"%{token}%"))
            conditions.append(lowered_column.op("%")(token))

    return or_(*conditions)


class SearchableMixin:
    """Adds ``Model.search_filter("query")`` using ``search_vector``."""

    __search_trgm_columns__: tuple[str, ...] = ()
    search_vector: Mapped[str | None]

    @classmethod
    def search_filter(cls, query: str):
        return build_search_condition(cls, query, cls.__search_trgm_columns__)


# ---------------------------------------------------------------------------
# Users and sessions
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    preferences: Mapped[dict[str, Any]] = _json_object_column()
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    sessions: Mapped[list[AuthSession]] = relationship(
        "AuthSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class AuthSession(Base):
    """Server-side session.

    Only the SHA-256 hash of the session token is persisted, so a database
    dump never yields a usable cookie. Rows are deleted by the user FK
    cascade and are checked for expiry and revocation on every request.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    user: Mapped[User] = relationship("User", back_populates="sessions")


# ---------------------------------------------------------------------------
# Companies and contacts
# ---------------------------------------------------------------------------


class Company(SearchableMixin, Base):
    __tablename__ = "companies"

    __search_trgm_columns__ = ("name", "domain", "industry", "city")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    sub_industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    headquarters: Mapped[str | None] = mapped_column(String(200), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technologies: Mapped[list[str] | None] = _json_list_column()
    funding_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_quality_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True
    )
    last_verified: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            _tsvector_expr(
                "name, website, domain, industry, sub_industry, city, country, "
                "headquarters, linkedin_url, notes, technologies::text"
            ),
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "data_quality_score >= 0 AND data_quality_score <= 100",
            name="ck_companies_quality_score",
        ),
        CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0",
            name="ck_companies_employee_count",
        ),
        CheckConstraint(
            "founded_year IS NULL OR (founded_year >= 1600 AND founded_year <= 2200)",
            name="ck_companies_founded_year",
        ),
        Index("ix_companies_search_vector", "search_vector", postgresql_using="gin"),
        _trgm_index("ix_companies_name_trgm", "name", "companies"),
        _trgm_index("ix_companies_domain_trgm", "domain", "companies"),
        Index("ix_companies_updated", "updated_at"),
        Index("ix_companies_archived_updated", "is_archived", "updated_at"),
    )

    creator = relationship("User", foreign_keys=[created_by_id], backref="companies_created")
    contacts: Mapped[list[Contact]] = relationship("Contact", back_populates="company", lazy="selectin")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary="company_tags", back_populates="companies", lazy="selectin")

    @hybrid_property
    def tag_names(self) -> list[str]:
        return [t.name for t in self.tags]


class Contact(SearchableMixin, Base):
    __tablename__ = "contacts"

    __search_trgm_columns__ = ("full_name", "email", "job_title", "company_name")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    job_title: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    email_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    phone_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: CRM pipeline stage: New, Contacted, Qualified, Proposal, Customer, Lost.
    #: Free text at the database level so future stages need no migration;
    #: the API validates against CRM_STAGES.
    stage: Mapped[str] = mapped_column(
        String(50), nullable=False, default="New", server_default=text("'New'"), index=True
    )
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    skills: Mapped[list[str] | None] = _json_list_column()
    employment_history: Mapped[list[dict[str, Any]] | None] = _json_list_column()
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_quality_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True
    )
    last_verified: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            _tsvector_expr(
                "full_name, first_name, last_name, job_title, department, seniority, "
                "email, phone, linkedin_url, company_name, city, country, notes"
            ),
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "data_quality_score >= 0 AND data_quality_score <= 100",
            name="ck_contacts_quality_score",
        ),
        Index("ix_contacts_search_vector", "search_vector", postgresql_using="gin"),
        _trgm_index("ix_contacts_full_name_trgm", "full_name", "contacts"),
        _trgm_index("ix_contacts_email_trgm", "email", "contacts"),
        Index("ix_contacts_company_id", "company_id"),
        Index("ix_contacts_updated", "updated_at"),
        Index("ix_contacts_archived_updated", "is_archived", "updated_at"),
        Index("ix_contacts_company_name", "company_name"),
    )

    company: Mapped[Company | None] = relationship("Company", back_populates="contacts", lazy="selectin")
    creator = relationship("User", foreign_keys=[created_by_id], backref="contacts_created")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary="contact_tags", back_populates="contacts", lazy="selectin")

    @hybrid_property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        if self.first_name:
            return self.first_name
        if self.last_name:
            return self.last_name
        return ""

    @hybrid_property
    def tag_names(self) -> list[str]:
        return [t.name for t in self.tags]


class ContactEmail(Base):
    __tablename__ = "contact_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        UniqueConstraint("contact_id", "email", name="uq_contact_emails_contact_email"),
        _trgm_index("ix_contact_emails_email_trgm", "email", "contact_emails"),
    )


class ContactPhone(Base):
    __tablename__ = "contact_phones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    phone_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("contact_id", "phone", name="uq_contact_phones_contact_phone"),)


class EmploymentHistory(Base):
    __tablename__ = "employment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_current: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()


#: CRM pipeline stages, in funnel order. Stored as plain text on contacts so
#: renaming is cheap; the API rejects anything outside this vocabulary.
CRM_STAGES: tuple[str, ...] = ("New", "Contacted", "Qualified", "Proposal", "Customer", "Lost")


class FollowUpTask(Base):
    """A CRM follow-up: call back, send proposal, schedule demo…

    Optionally linked to one contact and/or one company. Deleting the linked
    record detaches the task (SET NULL) instead of destroying the reminder.
    """

    __tablename__ = "follow_up_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False, index=True)
    done_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="ck_follow_up_tasks_title_not_blank"),
        Index("ix_follow_up_tasks_open_due", "done", "due_at"),
    )

    contact: Mapped[Contact | None] = relationship("Contact", lazy="selectin")
    company: Mapped[Company | None] = relationship("Company", lazy="selectin")


#: Lead lifecycle stages (qualification funnel), in order. The API validates
#: against this vocabulary so a typo can never enter the column.
LEAD_STAGES: tuple[str, ...] = ("New", "Working", "Qualified", "Unqualified", "Nurture", "Converted")

#: Lead working statuses. ``Disqualified`` is the explicit exit and ``Converted``
#: is set only by the conversion endpoint, never by hand.
LEAD_STATUSES: tuple[str, ...] = (
    "New",
    "Open",
    "Working",
    "Contacted",
    "Nurture",
    "Disqualified",
    "Converted",
)

#: Lead priorities, ordered from least to most urgent.
LEAD_PRIORITIES: tuple[str, ...] = ("Low", "Medium", "High", "Urgent")


class Lead(SearchableMixin, Base):
    """A prospect tracked from discovery through qualification.

    A lead is deliberately *not* a contact: it may never qualify, and the
    conversion endpoint is what creates or links the durable Contact and
    Company records. ``converted_contact_id`` / ``converted_company_id``
    preserve the trail so a converted lead is never silently duplicated.
    """

    __tablename__ = "leads"

    __search_trgm_columns__ = ("full_name", "email", "company_name", "job_title")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    job_title: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    email_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    phone_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    lead_source: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    #: Qualification funnel position, validated against LEAD_STAGES.
    lifecycle_stage: Mapped[str] = mapped_column(
        String(50), nullable=False, default="New", server_default=text("'New'"), index=True
    )
    #: Working status, validated against LEAD_STATUSES.
    lead_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="New", server_default=text("'New'"), index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Medium", server_default=text("'Medium'"), index=True
    )
    #: 0-100 fit + completeness score, and the per-rule breakdown that produced
    #: it, so the number is always explainable rather than a black box.
    lead_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False, index=True)
    score_breakdown: Mapped[list[dict[str, Any]] | None] = _json_list_column()
    score_updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    next_follow_up_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    consent_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Set when the prospect asked not to be contacted; the UI surfaces it and
    #: imports must not clear it.
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    disqualified_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    converted_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    converted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_quality_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True
    )
    last_verified: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            _tsvector_expr(
                "full_name, first_name, last_name, job_title, department, email, phone, "
                "linkedin_url, company_name, company_domain, industry, city, state, "
                "country, campaign, notes"
            ),
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("lead_score >= 0 AND lead_score <= 100", name="ck_leads_lead_score"),
        CheckConstraint(
            "data_quality_score >= 0 AND data_quality_score <= 100",
            name="ck_leads_quality_score",
        ),
        CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0",
            name="ck_leads_employee_count",
        ),
        CheckConstraint(
            "priority IN ('Low', 'Medium', 'High', 'Urgent')",
            name="ck_leads_priority",
        ),
        CheckConstraint(
            "converted_at IS NULL OR lead_status = 'Converted'",
            name="ck_leads_converted_consistency",
        ),
        Index("ix_leads_search_vector", "search_vector", postgresql_using="gin"),
        _trgm_index("ix_leads_full_name_trgm", "full_name", "leads"),
        _trgm_index("ix_leads_email_trgm", "email", "leads"),
        _trgm_index("ix_leads_company_name_trgm", "company_name", "leads"),
        Index("ix_leads_updated", "updated_at"),
        Index("ix_leads_archived_updated", "is_archived", "updated_at"),
        Index("ix_leads_stage_status", "lifecycle_stage", "lead_status"),
        Index("ix_leads_follow_up", "next_follow_up_at"),
    )

    company: Mapped[Company | None] = relationship("Company", foreign_keys=[company_id], lazy="selectin")
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    creator = relationship("User", foreign_keys=[created_by_id], backref="leads_created")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary="lead_tags", back_populates="leads", lazy="selectin")

    @hybrid_property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.first_name or self.last_name or self.email or ""

    @hybrid_property
    def tag_names(self) -> list[str]:
        return [t.name for t in self.tags]

    @hybrid_property
    def is_converted(self) -> bool:
        return self.converted_at is not None


class LeadTag(Base):
    __tablename__ = "lead_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="Cascade"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="Cascade"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("lead_id", "tag_id", name="uq_lead_tags_lead_tag"),)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_tags_name_not_blank"),
        _trgm_index("ix_tags_name_trgm", "name", "tags"),
    )

    contacts: Mapped[list[Contact]] = relationship(
        "Contact", secondary="contact_tags", back_populates="tags", lazy="selectin"
    )
    companies: Mapped[list[Company]] = relationship(
        "Company", secondary="company_tags", back_populates="tags", lazy="selectin"
    )
    leads: Mapped[list[Lead]] = relationship("Lead", secondary="lead_tags", back_populates="tags", lazy="selectin")


class ContactTag(Base):
    __tablename__ = "contact_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="Cascade"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("contact_id", "tag_id", name="uq_contact_tags_contact_tag"),)


class CompanyTag(Base):
    __tablename__ = "company_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="Cascade"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="Cascade"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("company_id", "tag_id", name="uq_company_tags_company_tag"),)


class ContactList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    creator = relationship("User", foreign_keys=[created_by_id], backref="lists_created")


class ListContact(Base):
    __tablename__ = "list_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id", ondelete="Cascade"), nullable=False, index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("list_id", "contact_id", name="uq_list_contacts_list_contact"),)


class ListCompany(Base):
    __tablename__ = "list_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id", ondelete="Cascade"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="Cascade"), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (UniqueConstraint("list_id", "company_id", name="uq_list_companies_list_company"),)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[list[dict[str, Any]]] = _json_list_column()
    scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (Index("ix_saved_searches_user", "created_by_id", "created_at"),)


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    columns: Mapped[list[str]] = _json_list_column()
    sort: Mapped[list[dict[str, Any]]] = _json_list_column()
    filters: Mapped[list[dict[str, Any]]] = _json_list_column()
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (Index("ix_saved_views_entity", "entity", "created_by_id"),)


# ---------------------------------------------------------------------------
# Import pipeline
# ---------------------------------------------------------------------------


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    file_mime: Mapped[str | None] = mapped_column(String(150), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default=text("'pending'"))
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: add | update | add_and_update | skip_duplicates
    strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="add_and_update", server_default=text("'add_and_update'")
    )
    #: fill_empty (never overwrite populated columns) | overwrite
    update_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="fill_empty", server_default=text("'fill_empty'")
    )
    sheet_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Worksheet names discovered in the uploaded workbook (XLSX/XLS only).
    sheet_names: Mapped[list[str] | None] = _json_list_column()
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_unchanged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_duplicate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_invalid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mapping: Mapped[dict[str, Any]] = _json_object_column()
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint(
            "strategy IN ('add', 'update', 'add_and_update', 'skip_duplicates')",
            name="ck_import_jobs_strategy",
        ),
        CheckConstraint("update_mode IN ('fill_empty', 'overwrite')", name="ck_import_jobs_update_mode"),
        Index("ix_import_jobs_user_created", "created_by_id", "created_at"),
    )

    creator = relationship("User", foreign_keys=[created_by_id], backref="imports_created")
    rows: Mapped[list[ImportRow]] = relationship(
        "ImportRow", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )
    errors: Mapped[list[ImportErrorRow]] = relationship(
        "ImportErrorRow", back_populates="job", lazy="selectin", cascade="all, delete-orphan"
    )


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="Cascade"), nullable=False, index=True
    )
    raw_row: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_row: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Per-field diff preview computed before a row is applied, e.g.
    #: {"email": {"from": "a@x.com", "to": "b@x.com", "action": "update"}}.
    update_preview: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    suggested_entity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    target_contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default=text("'pending'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        Index("ix_import_rows_job_status", "import_job_id", "status"),
        Index("ix_import_rows_job_index", "import_job_id", "row_index"),
    )

    job: Mapped[ImportJob] = relationship("ImportJob", back_populates="rows")


class ImportErrorRow(Base):
    """Structured, downloadable error report for a single import row."""

    __tablename__ = "import_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="Cascade"), nullable=False, index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="error", server_default=text("'error'"))
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (Index("ix_import_errors_job_row", "import_job_id", "row_index"),)

    job: Mapped[ImportJob] = relationship("ImportJob", back_populates="errors")


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    match_id: Mapped[int] = mapped_column(Integer, nullable=False)
    match_type: Mapped[str] = mapped_column(String(50), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open", server_default=text("'open'"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("entity_type IN ('company', 'contact')", name="ck_duplicate_candidates_entity_type"),
        CheckConstraint("match_score >= 0 AND match_score <= 1", name="ck_duplicate_candidates_score"),
        Index("ix_duplicate_candidates_entity", "entity_type", "record_id"),
        Index("ix_duplicate_candidates_status", "status"),
        Index("ix_duplicate_candidates_pair", "entity_type", "record_id", "match_id"),
    )


class VerificationEvent(Base):
    __tablename__ = "verification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (Index("ix_verification_events_entity", "entity_type", "entity_id"),)


#: Lifecycle of an outbound email. ``sent`` means the provider accepted it;
#: the rest arrive asynchronously through the provider's webhook.
EMAIL_STATUSES: tuple[str, ...] = (
    "sent",
    "delivered",
    "opened",
    "clicked",
    "delivery_delayed",
    "bounced",
    "complained",
    "failed",
)

#: Statuses that end the story: a later event must not walk them back.
TERMINAL_EMAIL_STATUSES: tuple[str, ...] = ("bounced", "complained", "failed")


class EmailMessage(Base):
    """One outbound email plus the delivery events the provider reports.

    The activity trail answers "who emailed whom"; this table answers "what
    happened to it", which is what the webhook updates. Rows are matched to
    webhook events on ``provider_message_id``.
    """

    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    #: The provider's own id for the message; the webhook correlation key.
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="sent", server_default=text("'sent'"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sent_at: Mapped[datetime.datetime] = _created_at_column()
    last_event_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Append-only audit of every event received, newest last.
    events: Mapped[list[Any]] = _json_array_column()
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        Index("ix_email_messages_contact_sent", "contact_id", "sent_at"),
        Index("ix_email_messages_provider_message", "provider", "provider_message_id"),
    )


#: Where a contact stands in a sequence. ``active`` is the only status the
#: dispatcher picks up; ``paused`` waits for a resume, the rest are final.
SEQUENCE_ENROLLMENT_STATUSES: tuple[str, ...] = (
    "active",
    "paused",
    "completed",
    "cancelled",
    "failed",
)

#: Statuses that mean "this contact is still working through the sequence".
#: A contact may only hold one such enrollment per sequence.
LIVE_SEQUENCE_STATUSES: tuple[str, ...] = ("active", "paused")


class EmailSequence(Base):
    """A named, ordered set of follow-up emails sent to a contact over time.

    The sequence itself is just the template; who is currently moving through it
    lives in :class:`EmailSequenceEnrollment`. Deleting the sequence cascades to
    both, because a step with no sequence is not meaningful.
    """

    __tablename__ = "email_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Pausing the sequence stops new sends without touching each enrollment.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="ck_email_sequences_name_not_blank"),)

    steps: Mapped[list[EmailSequenceStep]] = relationship(
        "EmailSequenceStep",
        back_populates="sequence",
        cascade="all, delete-orphan",
        order_by="EmailSequenceStep.position",
        lazy="selectin",
    )
    enrollments: Mapped[list[EmailSequenceEnrollment]] = relationship(
        "EmailSequenceEnrollment", back_populates="sequence", cascade="all, delete-orphan"
    )


class EmailSequenceStep(Base):
    """One email in a sequence, plus how long to wait before sending it.

    ``position`` is 0-based and contiguous; ``delay_days`` is the wait *before*
    this step, so step 0 normally has a delay of 0 and goes out on enrollment.
    """

    __tablename__ = "email_sequence_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("email_sequences.id", ondelete="Cascade"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        UniqueConstraint("sequence_id", "position", name="uq_email_sequence_steps_sequence_position"),
        CheckConstraint("position >= 0", name="ck_email_sequence_steps_position"),
        CheckConstraint("delay_days >= 0", name="ck_email_sequence_steps_delay"),
        CheckConstraint("length(btrim(subject)) > 0", name="ck_email_sequence_steps_subject_not_blank"),
    )

    sequence: Mapped[EmailSequence] = relationship("EmailSequence", back_populates="steps")


class EmailSequenceEnrollment(Base):
    """One contact's progress through one sequence.

    ``current_step`` is the index of the *next* step to send, so a completed
    enrollment has it equal to the number of steps. ``next_send_at`` is the only
    clock the dispatcher reads.
    """

    __tablename__ = "email_sequence_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(
        ForeignKey("email_sequences.id", ondelete="Cascade"), nullable=False, index=True
    )
    #: Deleting the contact ends their enrollments: there is no one left to mail.
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="Cascade"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default=text("'active'"), nullable=False, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    next_send_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Why the enrollment stopped, when it stopped for a reason other than "done".
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_email_sequence_enrollments_status",
        ),
        CheckConstraint("current_step >= 0", name="ck_email_sequence_enrollments_step"),
        # The dispatcher's only query: active enrollments that are due.
        Index("ix_email_sequence_enrollments_due", "status", "next_send_at"),
    )

    #: selectin, like ``contact``: an async session cannot lazy-load on demand,
    #: and every serializer here wants the sequence anyway.
    sequence: Mapped[EmailSequence] = relationship("EmailSequence", back_populates="enrollments", lazy="selectin")
    contact: Mapped[Contact] = relationship("Contact", lazy="selectin")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    _metadata: Mapped[dict[str, Any]] = _json_object_column()
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        Index("ix_activity_logs_created", "created_at"),
        Index("ix_activity_logs_user", "user_id", "created_at"),
        Index("ix_activity_logs_action", "action"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),)


class CustomField(Base):
    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    default_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        UniqueConstraint("entity_type", "key", name="uq_custom_fields_entity_key"),
        CheckConstraint("entity_type IN ('company', 'contact')", name="ck_custom_fields_entity_type"),
    )


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_field_id: Mapped[int] = mapped_column(
        ForeignKey("custom_fields.id", ondelete="Cascade"), nullable=False, index=True
    )
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "custom_field_id", name="uq_custom_field_values_entity_field"),
        Index("ix_custom_field_values_entity", "entity_type", "entity_id"),
    )


class Call(Base):
    """A logged phone call against a contact or company.

    Direction/outcome come from fixed vocabularies so reporting stays valid;
    duration is seconds, entered as minutes by the UI and stored raw.
    """

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # inbound | outbound
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)  # connected | voicemail | missed | scheduled
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_followup_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("direction IN ('inbound','outbound')", name="ck_calls_direction"),
        CheckConstraint("outcome IN ('connected','voicemail','missed','scheduled')", name="ck_calls_outcome"),
        Index("ix_calls_contact_created", "contact_id", "created_at"),
        Index("ix_calls_company_created", "company_id", "created_at"),
    )

    contact: Mapped[Contact | None] = relationship("Contact", lazy="selectin")
    company: Mapped[Company | None] = relationship("Company", lazy="selectin")


class Note(Base):
    """A workspace note on a company, contact or lead.

    ``pinned`` notes float to the top of the record page. Deleting the parent
    detaches (SET NULL), never destroys the note.
    """

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("length(btrim(body)) > 0", name="ck_notes_body_not_blank"),
        CheckConstraint(
            "(contact_id IS NOT NULL)::int + (company_id IS NOT NULL)::int + (lead_id IS NOT NULL)::int = 1",
            name="ck_notes_exactly_one_parent",
        ),
        Index("ix_notes_contact_created", "contact_id", "created_at"),
        Index("ix_notes_company_created", "company_id", "created_at"),
        Index("ix_notes_lead_created", "lead_id", "created_at"),
    )

    author: Mapped[User | None] = relationship("User", lazy="selectin")


class Campaign(Base):
    """A scheduled bulk-email blast to a contact list.

    Recipients are frozen at creation so late list edits cannot surprise later
    sends. Suppression (unsubscribed / bounced / replied) is enforced against
    e-mail status at enqueue time.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    list_id: Mapped[int | None] = mapped_column(ForeignKey("lists.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_campaigns_name_not_blank"),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')",
            name="ck_campaigns_status",
        ),
        Index("ix_campaigns_status", "status"),
    )


class CampaignRecipient(Base):
    """One frozen recipient of a campaign, with its delivery outcome."""

    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="Cascade"), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SetNull"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_campaign_recipients_campaign_email"),
        CheckConstraint("status IN ('pending','sent','failed','skipped','suppressed')", name="ck_campaign_recipient_status"),
    )


class SettingsRow(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = _created_at_column()
    updated_at: Mapped[datetime.datetime] = _updated_at_column()


#: Tables in dependency order for logical snapshot/restore, excluding the
#: alembic bookkeeping table.
SNAPSHOT_TABLES: tuple[str, ...] = (
    "users",
    "sessions",
    "tags",
    "companies",
    "contacts",
    "contact_emails",
    "contact_phones",
    "employment_history",
    "contact_tags",
    "company_tags",
    "leads",
    "lead_tags",
    "lists",
    "list_contacts",
    "list_companies",
    "saved_searches",
    "saved_views",
    "import_jobs",
    "import_rows",
    "import_errors",
    "duplicate_candidates",
    "verification_events",
    "follow_up_tasks",
    "calls",
    "notes",
    "campaigns",
    "campaign_recipients",
    "email_messages",
    "email_sequences",
    "email_sequence_steps",
    "email_sequence_enrollments",
    "activity_logs",
    "audit_logs",
    "custom_fields",
    "custom_field_values",
    "settings",
)
