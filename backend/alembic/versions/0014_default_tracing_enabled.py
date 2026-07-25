"""per-user execution-tracing default

Revision ID: 0014_default_tracing
Revises: 0013_admin_and_moderation
Create Date: 2026-07-25

Adds ``users.default_tracing_enabled``: seeds a task's tracing toggle when the
request leaves it unset. Falls through to the server-wide ``TRACING_ENABLED``
when false, so existing deployments are unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_default_tracing"
down_revision = "0013_admin_and_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_tracing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "default_tracing_enabled")
