"""remove trial and first-month discount

Revision ID: 0009_remove_trial_and_discount
Revises: 0008_email_verification
Create Date: 2026-07-12

The product no longer offers a free trial or a first-month discount. Every
account must hold an active, full-price subscription to run tasks.

Changes:
* Drop ``users.first_discount_used`` (the once-per-user discount flag).
* Flip any lingering ``subscriptions.status = 'trialing'`` rows to ``'inactive'``
  so lazy status resolution can no longer keep a grandfathered trial alive.

``subscriptions.trial_end`` is intentionally left in place (nullable, unused):
dropping it buys nothing and keeps the downgrade path simple.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_remove_trial_and_discount"
down_revision = "0008_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE subscriptions SET status = 'inactive' WHERE status = 'trialing'"
        )
    )
    op.drop_column("users", "first_discount_used")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "first_discount_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Trial rows cannot be reconstructed; the status flip is not reversed.
