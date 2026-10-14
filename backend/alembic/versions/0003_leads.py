"""Leads: a qualification funnel ahead of contacts and companies.

Revision ID: 0003_leads
Revises: 0002_crm_stage_tasks
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_leads"
down_revision: str | None = "0002_crm_stage_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Columns folded into the stored ``tsvector``. Kept in one place so the
#: generated expression here and in the model cannot drift.
_SEARCH_PARTS = (
    "full_name, first_name, last_name, job_title, department, email, phone, "
    "linkedin_url, company_name, company_domain, industry, city, state, "
    "country, campaign, notes"
)


def _search_expression() -> str:
    parts = [part.strip() for part in _SEARCH_PARTS.split(",")]
    return (
        "to_tsvector('english'::regconfig, "
        + " || ' ' || ".join(f"coalesce({part}, '')" for part in parts)
        + ")"
    )


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("first_name", sa.String(length=150), nullable=True),
        sa.Column("last_name", sa.String(length=150), nullable=True),
        sa.Column("full_name", sa.String(length=300), nullable=True),
        sa.Column("job_title", sa.String(length=300), nullable=True),
        sa.Column("department", sa.String(length=150), nullable=True),
        sa.Column("seniority", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("email_status", sa.String(length=50), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("phone_status", sa.String(length=50), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("company_name", sa.String(length=300), nullable=True),
        sa.Column("company_domain", sa.String(length=255), nullable=True),
        sa.Column("industry", sa.String(length=200), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("company_size", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("lead_source", sa.String(length=200), nullable=True),
        sa.Column("campaign", sa.String(length=200), nullable=True),
        sa.Column("lifecycle_stage", sa.String(length=50), server_default=sa.text("'New'"), nullable=False),
        sa.Column("lead_status", sa.String(length=50), server_default=sa.text("'New'"), nullable=False),
        sa.Column("priority", sa.String(length=20), server_default=sa.text("'Medium'"), nullable=False),
        sa.Column("lead_score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "score_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column("score_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_status", sa.String(length=50), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("disqualified_reason", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("converted_contact_id", sa.Integer(), nullable=True),
        sa.Column("converted_company_id", sa.Integer(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_quality_score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_verified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_search_expression(), persisted=True),
            nullable=True,
        ),
        sa.CheckConstraint("lead_score >= 0 AND lead_score <= 100", name="ck_leads_lead_score"),
        sa.CheckConstraint(
            "data_quality_score >= 0 AND data_quality_score <= 100", name="ck_leads_quality_score"
        ),
        sa.CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0", name="ck_leads_employee_count"
        ),
        sa.CheckConstraint("priority IN ('Low', 'Medium', 'High', 'Urgent')", name="ck_leads_priority"),
        sa.CheckConstraint(
            "converted_at IS NULL OR lead_status = 'Converted'", name="ck_leads_converted_consistency"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_leads_full_name"), "leads", ["full_name"], unique=False)
    op.create_index(op.f("ix_leads_job_title"), "leads", ["job_title"], unique=False)
    op.create_index(op.f("ix_leads_email"), "leads", ["email"], unique=False)
    op.create_index(op.f("ix_leads_phone"), "leads", ["phone"], unique=False)
    op.create_index(op.f("ix_leads_company_name"), "leads", ["company_name"], unique=False)
    op.create_index(op.f("ix_leads_company_domain"), "leads", ["company_domain"], unique=False)
    op.create_index(op.f("ix_leads_industry"), "leads", ["industry"], unique=False)
    op.create_index(op.f("ix_leads_city"), "leads", ["city"], unique=False)
    op.create_index(op.f("ix_leads_country"), "leads", ["country"], unique=False)
    op.create_index(op.f("ix_leads_lead_source"), "leads", ["lead_source"], unique=False)
    op.create_index(op.f("ix_leads_campaign"), "leads", ["campaign"], unique=False)
    op.create_index(op.f("ix_leads_lifecycle_stage"), "leads", ["lifecycle_stage"], unique=False)
    op.create_index(op.f("ix_leads_lead_status"), "leads", ["lead_status"], unique=False)
    op.create_index(op.f("ix_leads_priority"), "leads", ["priority"], unique=False)
    op.create_index(op.f("ix_leads_lead_score"), "leads", ["lead_score"], unique=False)
    op.create_index(op.f("ix_leads_owner_id"), "leads", ["owner_id"], unique=False)
    op.create_index(op.f("ix_leads_company_id"), "leads", ["company_id"], unique=False)
    op.create_index(op.f("ix_leads_next_follow_up_at"), "leads", ["next_follow_up_at"], unique=False)
    op.create_index(op.f("ix_leads_converted_contact_id"), "leads", ["converted_contact_id"], unique=False)
    op.create_index(op.f("ix_leads_converted_company_id"), "leads", ["converted_company_id"], unique=False)
    op.create_index(op.f("ix_leads_is_archived"), "leads", ["is_archived"], unique=False)

    op.create_index("ix_leads_search_vector", "leads", ["search_vector"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_leads_full_name_trgm",
        "leads",
        [sa.literal_column("lower(full_name) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_leads_email_trgm",
        "leads",
        [sa.literal_column("lower(email) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_leads_company_name_trgm",
        "leads",
        [sa.literal_column("lower(company_name) gin_trgm_ops")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("ix_leads_updated", "leads", ["updated_at"], unique=False)
    op.create_index("ix_leads_archived_updated", "leads", ["is_archived", "updated_at"], unique=False)
    op.create_index("ix_leads_stage_status", "leads", ["lifecycle_stage", "lead_status"], unique=False)
    op.create_index("ix_leads_follow_up", "leads", ["next_follow_up_at"], unique=False)

    op.create_table(
        "lead_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "tag_id", name="uq_lead_tags_lead_tag"),
    )
    op.create_index(op.f("ix_lead_tags_lead_id"), "lead_tags", ["lead_id"], unique=False)
    op.create_index(op.f("ix_lead_tags_tag_id"), "lead_tags", ["tag_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_tags_tag_id"), table_name="lead_tags")
    op.drop_index(op.f("ix_lead_tags_lead_id"), table_name="lead_tags")
    op.drop_table("lead_tags")

    op.drop_index("ix_leads_follow_up", table_name="leads")
    op.drop_index("ix_leads_stage_status", table_name="leads")
    op.drop_index("ix_leads_archived_updated", table_name="leads")
    op.drop_index("ix_leads_updated", table_name="leads")
    op.drop_index("ix_leads_company_name_trgm", table_name="leads", postgresql_using="gin")
    op.drop_index("ix_leads_email_trgm", table_name="leads", postgresql_using="gin")
    op.drop_index("ix_leads_full_name_trgm", table_name="leads", postgresql_using="gin")
    op.drop_index("ix_leads_search_vector", table_name="leads", postgresql_using="gin")
    op.drop_index(op.f("ix_leads_is_archived"), table_name="leads")
    op.drop_index(op.f("ix_leads_converted_company_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_converted_contact_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_next_follow_up_at"), table_name="leads")
    op.drop_index(op.f("ix_leads_company_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_owner_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_lead_score"), table_name="leads")
    op.drop_index(op.f("ix_leads_priority"), table_name="leads")
    op.drop_index(op.f("ix_leads_lead_status"), table_name="leads")
    op.drop_index(op.f("ix_leads_lifecycle_stage"), table_name="leads")
    op.drop_index(op.f("ix_leads_campaign"), table_name="leads")
    op.drop_index(op.f("ix_leads_lead_source"), table_name="leads")
    op.drop_index(op.f("ix_leads_country"), table_name="leads")
    op.drop_index(op.f("ix_leads_city"), table_name="leads")
    op.drop_index(op.f("ix_leads_industry"), table_name="leads")
    op.drop_index(op.f("ix_leads_company_domain"), table_name="leads")
    op.drop_index(op.f("ix_leads_company_name"), table_name="leads")
    op.drop_index(op.f("ix_leads_phone"), table_name="leads")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_index(op.f("ix_leads_job_title"), table_name="leads")
    op.drop_index(op.f("ix_leads_full_name"), table_name="leads")
    op.drop_table("leads")
