"""profile personalization, preferences, 2FA, and session context

Revision ID: 0007_profile_2fa_sessions
Revises: 0006_refresh_tokens
Create Date: 2026-07-12

Adds:
* users: bio / avatar / timezone / reviewer-default / TOTP columns
* refresh_tokens: login context (user_agent, ip_address, last_used_at)
* recovery_codes: single-use 2FA backup codes (Argon2 hashes)
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "0007_profile_2fa_sessions"
down_revision = "0006_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: personalization, preferences, 2FA ---
    op.add_column("users", sa.Column("bio", sa.String(length=280), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_color", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "users", sa.Column("avatar_emoji", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "users", sa.Column("timezone", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "default_reviewer_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users", sa.Column("totp_secret", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # --- refresh_tokens: login context for the Active Sessions view ---
    op.add_column(
        "refresh_tokens",
        sa.Column("user_agent", sa.String(length=400), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("ip_address", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- recovery_codes: single-use 2FA backup codes ---
    op.create_table(
        "recovery_codes",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        comment="Single-use two-factor recovery codes (Argon2 hashes)",
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")

    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "ip_address")
    op.drop_column("refresh_tokens", "user_agent")

    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "default_reviewer_enabled")
    op.drop_column("users", "timezone")
    op.drop_column("users", "avatar_emoji")
    op.drop_column("users", "avatar_color")
    op.drop_column("users", "bio")
