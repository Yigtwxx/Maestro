"""billing and quota: subscriptions, payment_methods, usage_records

Drops the notion of a free tier. Existing users are grandfathered into a
14-day Starter trial rather than being locked out.

Revision ID: 0003_billing_and_quota
Revises: 0002_user_default_provider
Create Date: 2026-07-10

"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

from app.core.constants import (
    PAYMENT_PROVIDER_MOCK,
    TRIAL_DURATION_DAYS,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.base import GUID

revision = "0003_billing_and_quota"
down_revision = "0002_user_default_provider"
branch_labels = None
depends_on = None

_LEGACY_FREE_TIER = "free"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "first_discount_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        "users",
        "subscription_tier",
        existing_type=sa.String(length=20),
        server_default=SubscriptionPlan.STARTER.value,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=20),
            nullable=False,
            server_default=PAYMENT_PROVIDER_MOCK,
        ),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=True
    )

    op.create_table(
        "payment_methods",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=20),
            nullable=False,
            server_default=PAYMENT_PROVIDER_MOCK,
        ),
        sa.Column("provider_payment_method_id", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=20), nullable=False),
        sa.Column("last4", sa.String(length=4), nullable=False),
        sa.Column("exp_month", sa.Integer(), nullable=False),
        sa.Column("exp_year", sa.Integer(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"])

    op.create_table(
        "usage_records",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_usage_records_task_id", "usage_records", ["task_id"], unique=True)
    op.create_index(
        "ix_usage_records_user_period", "usage_records", ["user_id", "period_start"]
    )

    _grandfather_existing_users()


def _grandfather_existing_users() -> None:
    """Give every pre-existing account a fresh Starter trial."""
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE users SET subscription_tier = :plan WHERE subscription_tier = :legacy"),
        {"plan": SubscriptionPlan.STARTER.value, "legacy": _LEGACY_FREE_TIER},
    )

    user_ids = conn.execute(sa.text("SELECT id FROM users")).scalars().all()
    if not user_ids:
        return

    now = datetime.now(UTC)
    trial_end = now + timedelta(days=TRIAL_DURATION_DAYS)
    subscriptions = sa.table(
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
    op.bulk_insert(
        subscriptions,
        [
            {
                "id": uuid.uuid4(),
                "user_id": uuid.UUID(str(user_id)),
                "plan": SubscriptionPlan.STARTER.value,
                "status": SubscriptionStatus.TRIALING.value,
                "provider": PAYMENT_PROVIDER_MOCK,
                "current_period_start": now,
                "current_period_end": trial_end,
                "trial_end": trial_end,
                "cancel_at_period_end": False,
                "created_at": now,
                "updated_at": now,
            }
            for user_id in user_ids
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_records_user_period", table_name="usage_records")
    op.drop_index("ix_usage_records_task_id", table_name="usage_records")
    op.drop_table("usage_records")

    op.drop_index("ix_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.alter_column(
        "users",
        "subscription_tier",
        existing_type=sa.String(length=20),
        server_default=_LEGACY_FREE_TIER,
    )
    op.drop_column("users", "first_discount_used")
