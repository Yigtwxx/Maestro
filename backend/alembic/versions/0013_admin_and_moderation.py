"""users.role + users.suspended_at (admin & moderation)

Revision ID: 0013_admin_and_moderation
Revises: 0012_nullable_subscription_tier
Create Date: 2026-07-13

Adds the platform's first authorization role plus a moderator-applied account
suspension flag:

* ``users.role`` — ``'user'`` (default) or ``'admin'``. Admin unlocks the
  moderation surface, an unmetered task quota, and the email-verification
  bypass. Every existing account backfills to ``'user'`` via the server default.
* ``users.suspended_at`` — NULL = active; a timestamp means a moderator locked
  the account out of the product surface (enforced in deps.get_active_user).
  Unlike ``deletion_requested_at`` it is not user-cancelable.

Note: the test suite builds its schema via ``Base.metadata.create_all``, so this
migration is not exercised by pytest — keep it in sync with the ORM columns on
``app.models.user.User`` by hand.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_admin_and_moderation"
down_revision = "0012_nullable_subscription_tier"
branch_labels = None
depends_on = None

# Pinned locally so later enum edits cannot rewrite Alembic history.
_ROLE_USER = "user"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default=_ROLE_USER,
        ),
    )
    op.add_column(
        "users",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_users_suspended_at"), "users", ["suspended_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_suspended_at"), table_name="users")
    op.drop_column("users", "suspended_at")
    op.drop_column("users", "role")
