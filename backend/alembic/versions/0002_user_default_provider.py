"""add users.default_provider (default LLM brain for tasks)

Revision ID: 0002_user_default_provider
Revises: 0001_initial
Create Date: 2026-07-09

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_user_default_provider"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("default_provider", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "default_provider")
