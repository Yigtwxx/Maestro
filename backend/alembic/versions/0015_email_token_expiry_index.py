"""index email_tokens.expires_at for the retention sweep

Revision ID: 0015_email_token_expiry_index
Revises: 0014_default_tracing
Create Date: 2026-07-29

``app.scripts.purge_email_tokens`` sweeps on ``expires_at < cutoff`` alone.
Without this index that predicate is a full scan of the very table the sweep
exists to bound. The existing ``user_id`` and unique ``token_hash`` indexes
cover the other two query shapes and are left alone.

The test suite builds its schema with ``Base.metadata.create_all``, so this
migration is never exercised by pytest -- keep it in sync with the ORM by hand.
"""

from __future__ import annotations

from alembic import op

revision = "0015_email_token_expiry_index"
down_revision = "0014_default_tracing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_email_tokens_expires_at", "email_tokens", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_email_tokens_expires_at", table_name="email_tokens")
