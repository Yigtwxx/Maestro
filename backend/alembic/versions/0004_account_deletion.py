"""account deletion: 30-day grace period flag

Adds ``users.deletion_requested_at``. NULL means the account is active; a
timestamp means it is locked and scheduled for an irreversible purge
ACCOUNT_DELETION_GRACE_DAYS later (GDPR Art.17 / KVKK Art.7).

The index backs the purge sweep's due-account query. It is a plain b-tree
rather than a partial index so the same DDL runs on SQLite (test suite).

Revision ID: 0004_account_deletion
Revises: 0003_billing_and_quota
Create Date: 2026-07-10

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_account_deletion"
down_revision = "0003_billing_and_quota"
branch_labels = None
depends_on = None

_INDEX = "ix_users_deletion_requested_at"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(_INDEX, "users", ["deletion_requested_at"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="users")
    op.drop_column("users", "deletion_requested_at")
