"""Calls, notes and email campaigns (new CRM features)

Revision ID: 0006_crm_engagement
Revises: 0005_email_sequences
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_crm_engagement"
down_revision = "0005_email_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("scheduled_followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("direction IN ('inbound','outbound')", name="ck_calls_direction"),
        sa.CheckConstraint("outcome IN ('connected','voicemail','missed','scheduled')", name="ck_calls_outcome"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calls_contact_id", "calls", ["contact_id"])
    op.create_index("ix_calls_company_id", "calls", ["company_id"])
    op.create_index("ix_calls_contact_created", "calls", ["contact_id", "created_at"])
    op.create_index("ix_calls_company_created", "calls", ["company_id", "created_at"])

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(btrim(body)) > 0", name="ck_notes_body_not_blank"),
        sa.CheckConstraint(
            "(contact_id IS NOT NULL)::int + (company_id IS NOT NULL)::int + (lead_id IS NOT NULL)::int = 1",
            name="ck_notes_exactly_one_parent",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_contact_id", "notes", ["contact_id"])
    op.create_index("ix_notes_company_id", "notes", ["company_id"])
    op.create_index("ix_notes_lead_id", "notes", ["lead_id"])
    op.create_index("ix_notes_contact_created", "notes", ["contact_id", "created_at"])
    op.create_index("ix_notes_company_created", "notes", ["company_id", "created_at"])
    op.create_index("ix_notes_lead_created", "notes", ["lead_id", "created_at"])

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("list_id", sa.Integer(), sa.ForeignKey("lists.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_campaigns_name_not_blank"),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')",
            name="ck_campaigns_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "campaign_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','skipped','suppressed')",
            name="ck_campaign_recipient_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "email", name="uq_campaign_recipients_campaign_email"),
    )
    op.create_index("ix_campaign_recipients_campaign_id", "campaign_recipients", ["campaign_id"])
    op.create_index("ix_campaign_recipients_contact_id", "campaign_recipients", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_recipients_contact_id", table_name="campaign_recipients")
    op.drop_index("ix_campaign_recipients_campaign_id", table_name="campaign_recipients")
    op.drop_table("campaign_recipients")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("ix_notes_lead_created", table_name="notes")
    op.drop_index("ix_notes_company_created", table_name="notes")
    op.drop_index("ix_notes_contact_created", table_name="notes")
    op.drop_index("ix_notes_lead_id", table_name="notes")
    op.drop_index("ix_notes_company_id", table_name="notes")
    op.drop_index("ix_notes_contact_id", table_name="notes")
    op.drop_table("notes")
    op.drop_index("ix_calls_company_created", table_name="calls")
    op.drop_index("ix_calls_contact_created", table_name="calls")
    op.drop_index("ix_calls_company_id", table_name="calls")
    op.drop_index("ix_calls_contact_id", table_name="calls")
    op.drop_table("calls")
