"""Email sequences: multi-step follow-ups and each contact's progress.

A sequence is a template (steps) plus a queue of enrollments, each carrying the
clock the dispatcher reads. Nothing here sends mail by itself; the tables exist
so progress survives a restart.

Revision ID: 0005_email_sequences
Revises: 0004_email_messages
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_email_sequences"
down_revision: str | None = "0004_email_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_sequences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_email_sequences_name_not_blank"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_sequences_is_active"), "email_sequences", ["is_active"])

    op.create_table(
        "email_sequence_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sequence_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("delay_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_email_sequence_steps_position"),
        sa.CheckConstraint("delay_days >= 0", name="ck_email_sequence_steps_delay"),
        sa.CheckConstraint("length(btrim(subject)) > 0", name="ck_email_sequence_steps_subject_not_blank"),
        sa.ForeignKeyConstraint(["sequence_id"], ["email_sequences.id"], ondelete="Cascade"),
        sa.PrimaryKeyConstraint("id"),
        # Steps are matched to their slot by position, so two step 2s would make
        # "which email goes next" ambiguous.
        sa.UniqueConstraint("sequence_id", "position", name="uq_email_sequence_steps_sequence_position"),
    )
    op.create_index(op.f("ix_email_sequence_steps_sequence_id"), "email_sequence_steps", ["sequence_id"])

    op.create_table(
        "email_sequence_enrollments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sequence_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("current_step", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_email_sequence_enrollments_status",
        ),
        sa.CheckConstraint("current_step >= 0", name="ck_email_sequence_enrollments_step"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="Cascade"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sequence_id"], ["email_sequences.id"], ondelete="Cascade"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_sequence_enrollments_sequence_id"), "email_sequence_enrollments", ["sequence_id"])
    op.create_index(op.f("ix_email_sequence_enrollments_contact_id"), "email_sequence_enrollments", ["contact_id"])
    op.create_index(op.f("ix_email_sequence_enrollments_status"), "email_sequence_enrollments", ["status"])
    # The dispatcher's only query: who is active and due.
    op.create_index("ix_email_sequence_enrollments_due", "email_sequence_enrollments", ["status", "next_send_at"])


def downgrade() -> None:
    op.drop_index("ix_email_sequence_enrollments_due", table_name="email_sequence_enrollments")
    op.drop_index(op.f("ix_email_sequence_enrollments_status"), table_name="email_sequence_enrollments")
    op.drop_index(op.f("ix_email_sequence_enrollments_contact_id"), table_name="email_sequence_enrollments")
    op.drop_index(op.f("ix_email_sequence_enrollments_sequence_id"), table_name="email_sequence_enrollments")
    op.drop_table("email_sequence_enrollments")
    op.drop_index(op.f("ix_email_sequence_steps_sequence_id"), table_name="email_sequence_steps")
    op.drop_table("email_sequence_steps")
    op.drop_index(op.f("ix_email_sequences_is_active"), table_name="email_sequences")
    op.drop_table("email_sequences")
