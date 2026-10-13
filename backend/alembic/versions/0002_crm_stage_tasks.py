"""CRM stage on contacts plus follow-up tasks.

Revision ID: 0002_crm_stage_tasks
Revises: 0001_initial
Create Date: 2026-10-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_crm_stage_tasks"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("stage", sa.String(length=50), server_default=sa.text("'New'"), nullable=False),
    )
    op.create_index(op.f("ix_contacts_stage"), "contacts", ["stage"], unique=False)

    op.create_table(
        "follow_up_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_follow_up_tasks_title_not_blank"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_follow_up_tasks_company_id"), "follow_up_tasks", ["company_id"], unique=False)
    op.create_index(op.f("ix_follow_up_tasks_contact_id"), "follow_up_tasks", ["contact_id"], unique=False)
    op.create_index(op.f("ix_follow_up_tasks_done"), "follow_up_tasks", ["done"], unique=False)
    op.create_index(op.f("ix_follow_up_tasks_due_at"), "follow_up_tasks", ["due_at"], unique=False)
    op.create_index("ix_follow_up_tasks_open_due", "follow_up_tasks", ["done", "due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_open_due", table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_due_at"), table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_done"), table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_contact_id"), table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_company_id"), table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")
    op.drop_index(op.f("ix_contacts_stage"), table_name="contacts")
    op.drop_column("contacts", "stage")
