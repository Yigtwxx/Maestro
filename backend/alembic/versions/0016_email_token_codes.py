"""numeric verification codes on email_tokens

Revision ID: 0016_email_token_codes
Revises: 0015_email_token_expiry_index
Create Date: 2026-07-29

Every verification email now carries a typeable 6-digit code beside the link,
for a user reading mail on a different device. The code lives on the same row
as the token so redeeming either one retires both (``used_at`` is shared), but
it gets its own expiry and an attempt counter: six digits is a guessable
keyspace where a 256-bit token is not.

All three columns are nullable or defaulted, so existing rows -- and the
password-reset purpose, which deliberately stays link-only -- are unaffected.

The test suite builds its schema with ``Base.metadata.create_all``, so this
migration is never exercised by pytest -- keep it in sync with the ORM by hand.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_email_token_codes"
down_revision = "0015_email_token_expiry_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_tokens", sa.Column("code_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "email_tokens",
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_tokens",
        sa.Column(
            "code_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("email_tokens", "code_attempts")
    op.drop_column("email_tokens", "code_expires_at")
    op.drop_column("email_tokens", "code_hash")
