"""email verification + single-use email action tokens

Revision ID: 0008_email_verification
Revises: 0007_profile_2fa_sessions
Create Date: 2026-07-12

Adds:
* users.email_verified (bool, default false)
* email_tokens: single-use verification / password-reset tokens (SHA-256)
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "0008_email_verification"
down_revision = "0007_profile_2fa_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "email_tokens",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        comment="Single-use email action tokens (SHA-256 hashes)",
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index(
        "ix_email_tokens_token_hash", "email_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_email_tokens_token_hash", table_name="email_tokens")
    op.drop_index("ix_email_tokens_user_id", table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_column("users", "email_verified")
