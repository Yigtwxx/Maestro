"""refresh token rotation: refresh_tokens table

Revision ID: 0006_refresh_tokens
Revises: 0005_api_key_endpoint
Create Date: 2026-07-11

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "0006_refresh_tokens"
down_revision = "0005_api_key_endpoint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("family_id", GUID(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        comment="Server-side refresh-token records for rotation + reuse-detection",
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
