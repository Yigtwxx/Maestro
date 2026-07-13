"""subscription_tier: NULL = no active subscription

Revision ID: 0012_nullable_subscription_tier
Revises: 0011_model_prefs
Create Date: 2026-07-13

Registration no longer creates a subscription, yet ``users.subscription_tier``
was born with a ``'starter'`` default — so accounts that never subscribed
displayed as starter-plan users everywhere the cache is read (sidebar,
profile). Make the column nullable with no default: NULL means "no active
subscription"; billing_service keeps it in sync on subscribe.

Backfill: NULL the cache for users whose subscription is effectively inactive
(no row, an inactive status, or canceled past its period end). Canceled-but-
not-yet-expired users keep their tier, matching the lazy display status.

Note: the test suite builds its schema via ``Base.metadata.create_all``, so
this backfill is not exercised by pytest — review it as SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0012_nullable_subscription_tier"
down_revision = "0011_model_prefs"
branch_labels = None
depends_on = None

# Pinned locally so later enum changes cannot rewrite Alembic history
# (same precedent as 0009's literal statuses and 0003's literal trial days).
_STARTER = "starter"


def upgrade() -> None:
    op.alter_column(
        "users",
        "subscription_tier",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE users SET subscription_tier = NULL "
            "WHERE id NOT IN ("
            "  SELECT user_id FROM subscriptions"
            "  WHERE status IN ('active', 'past_due')"
            "     OR (status = 'canceled' AND current_period_end > :now)"
            ")"
        ),
        {"now": datetime.now(UTC)},
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE users SET subscription_tier = 'starter' "
            "WHERE subscription_tier IS NULL"
        )
    )
    op.alter_column(
        "users",
        "subscription_tier",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=_STARTER,
    )
