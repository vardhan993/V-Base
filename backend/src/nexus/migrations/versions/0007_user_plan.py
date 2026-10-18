"""User plans (INR billing tiers; admin emails are free)

Revision ID: 0007_user_plan
Revises: 0006_crm_engagement
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_user_plan"
down_revision = "0006_crm_engagement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan", sa.String(length=30), nullable=False, server_default="starter"))
    op.create_check_constraint(
        "ck_users_plan",
        "users",
        "plan IN ('admin','starter','growth','scale')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_plan", "users", type_="check")
    op.drop_column("users", "plan")
