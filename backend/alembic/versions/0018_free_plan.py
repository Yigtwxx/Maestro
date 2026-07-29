"""put every account on the active free plan

Revision ID: 0018_free_plan
Revises: 0017_email_token_new_email
Create Date: 2026-07-29

The product now ships a FREE plan with an unlimited token allowance, and every
account is provisioned with it at registration. This backfills the accounts that
already exist so they are not left on the old "no subscription => 402 on task
start" path.

Three effects worth stating plainly:

1. Every non-active subscription is converted to an active free one. This is
   **not reversible**. It is safe only because billing was never live in this
   build -- ``PAYMENT_PROVIDER=mock`` and ``BILLING_LIVE = false`` mean no real
   money was ever taken, so no paid entitlement is being destroyed.
2. Resetting ``current_period_start`` orphans those users' existing
   ``usage_records`` from the period sum (``usage_service`` filters on exact
   equality). Harmless: free is unlimited, so nothing sums against a cap.
3. The test suite builds its schema with ``Base.metadata.create_all``, so this
   backfill is never exercised by pytest -- only by the CI smoke job, which runs
   ``alembic upgrade head`` against real Postgres. Review it as SQL.

Plan/status literals are pinned locally rather than imported from
``app.core.constants`` so a later enum change cannot rewrite Alembic history
(same convention as 0012).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "0018_free_plan"
down_revision = "0017_email_token_new_email"
branch_labels = None
depends_on = None

_FREE = "free"
_ACTIVE = "active"
_MOCK = "mock"
_BILLING_PERIOD_DAYS = 30


def _subscriptions_table() -> sa.TableClause:
    """Column list for the bulk insert (mirrors 0003's grandfather helper)."""
    return sa.table(
        "subscriptions",
        sa.column("id", GUID()),
        sa.column("user_id", GUID()),
        sa.column("plan", sa.String()),
        sa.column("status", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("current_period_start", sa.DateTime(timezone=True)),
        sa.column("current_period_end", sa.DateTime(timezone=True)),
        sa.column("trial_end", sa.DateTime(timezone=True)),
        sa.column("cancel_at_period_end", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    period_end = now + timedelta(days=_BILLING_PERIOD_DAYS)
    params = {"free": _FREE, "active": _ACTIVE, "mock": _MOCK, "now": now}

    # 1. Every lapsed/canceled/inactive row becomes an active free one.
    conn.execute(
        sa.text(
            "UPDATE subscriptions SET plan = :free, status = :active, "
            "provider = :mock, provider_subscription_id = NULL, "
            "provider_customer_id = NULL, trial_end = NULL, "
            "current_period_start = :now, current_period_end = :period_end, "
            "cancel_at_period_end = false, updated_at = :now "
            "WHERE status <> :active"
        ),
        {**params, "period_end": period_end},
    )

    # 2. Seed a free row for every account that has none. id/created_at/
    #    updated_at are generated Python-side by the ORM (_uuid_pk,
    #    TimestampMixin), never by a server_default, so supply them here.
    user_ids = (
        conn.execute(
            sa.text(
                "SELECT id FROM users u WHERE NOT EXISTS "
                "(SELECT 1 FROM subscriptions s WHERE s.user_id = u.id)"
            )
        )
        .scalars()
        .all()
    )
    if user_ids:
        op.bulk_insert(
            _subscriptions_table(),
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": uuid.UUID(str(user_id)),
                    "plan": _FREE,
                    "status": _ACTIVE,
                    "provider": _MOCK,
                    "current_period_start": now,
                    "current_period_end": period_end,
                    "trial_end": None,
                    "cancel_at_period_end": False,
                    "created_at": now,
                    "updated_at": now,
                }
                for user_id in user_ids
            ],
        )

    # 3. Re-sync the display cache from the authoritative row.
    conn.execute(
        sa.text(
            "UPDATE users SET subscription_tier = s.plan FROM subscriptions s "
            "WHERE s.user_id = users.id"
        )
    )


def downgrade() -> None:
    """Remove the free rows. Paid plans converted in step 1 do not come back."""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM subscriptions WHERE plan = :free"), {"free": _FREE}
    )
    conn.execute(
        sa.text(
            "UPDATE users SET subscription_tier = NULL WHERE subscription_tier = :free"
        ),
        {"free": _FREE},
    )
