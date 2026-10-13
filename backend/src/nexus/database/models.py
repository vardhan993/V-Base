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
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="New", server_default=text("'New'"), index=True)
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
    "activity_logs",
    "audit_logs",
    "custom_fields",
    "custom_field_values",
    "settings",
)
