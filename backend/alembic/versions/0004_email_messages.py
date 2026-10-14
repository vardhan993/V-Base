"""Outbound email messages and their delivery events.

The activity trail records that an email was sent; this table records what
happened to it afterwards, so a provider webhook has somewhere to land.

Revision ID: 0004_email_messages
Revises: 0003_leads
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_email_messages"
down_revision: str | None = "0003_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("from_email", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'sent'"), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('sent', 'delivered', 'opened', 'clicked', 'delivery_delayed', 'bounced', "
            "'complained', 'failed')",
            name="ck_email_messages_status",
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_messages_provider_message_id"), "email_messages", ["provider_message_id"])
    op.create_index(op.f("ix_email_messages_status"), "email_messages", ["status"])
    op.create_index(op.f("ix_email_messages_contact_id"), "email_messages", ["contact_id"])
    # Detail routes read one contact's thread newest-first.
    op.create_index("ix_email_messages_contact_sent", "email_messages", ["contact_id", "sent_at"])
    # The webhook matches on (provider, provider_message_id).
    op.create_index(
        "ix_email_messages_provider_message", "email_messages", ["provider", "provider_message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_messages_provider_message", table_name="email_messages")
    op.drop_index("ix_email_messages_contact_sent", table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_contact_id"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_status"), table_name="email_messages")
    op.drop_index(op.f("ix_email_messages_provider_message_id"), table_name="email_messages")
    op.drop_table("email_messages")
