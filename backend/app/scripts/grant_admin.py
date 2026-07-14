"""Promote accounts to full-privilege admins (owner / moderation accounts).

Run with ``python -m app.scripts.grant_admin --email you@example.com`` from
``backend/``. Emails may also come from the ``GRANT_ADMIN_EMAILS`` env var
(comma-separated); CLI ``--email`` flags and the env list are merged.

For each target the script (idempotently):

* sets ``role = 'admin'`` and ``email_verified = True``;
* seeds an **active** ``scale`` subscription (the top plan) if the account has
  no active one, so the billing UI reflects full access. Admins also run
  unmetered (``quota_service.is_unmetered``), so this subscription is for
  display/consistency — task start never depends on it.

No password is ever handled here (CLAUDE.md security rules): the account must be
registered first through the normal ``/register`` flow, then promoted. If a
target email has no account the script reports it and moves on.

Why a script and not an endpoint: bootstrapping the *first* admin cannot itself
require an admin, and account promotion is a rare operator action, not a product
feature.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    BILLING_PERIOD_DAYS,
    PAYMENT_PROVIDER_MOCK,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)
from app.core.database import SessionLocal, close_connections
from app.models.subscription import Subscription
from app.models.user import User
from app.services import billing_service

logger = logging.getLogger(__name__)

_ENV_EMAILS = "GRANT_ADMIN_EMAILS"


def _collect_emails(cli_emails: list[str]) -> list[str]:
    """Merge --email flags with the GRANT_ADMIN_EMAILS env var, deduped."""
    raw = list(cli_emails)
    env_value = os.environ.get(_ENV_EMAILS, "")
    raw.extend(part for part in env_value.split(",") if part.strip())
    seen: dict[str, None] = {}
    for email in raw:
        normalized = email.strip().lower()
        if normalized:
            seen.setdefault(normalized, None)
    return list(seen)


async def _seed_scale_subscription(
    db: AsyncSession, user: User, *, now: datetime
) -> str:
    """Ensure the user holds an active scale subscription. Returns a status word."""
    subscription = await billing_service.get_subscription(db, user.id)
    plan = SubscriptionPlan.SCALE.value
    if subscription is not None and billing_service.is_active(subscription):
        # Already active — only ensure it is the top plan for full quota display.
        if subscription.plan != plan:
            subscription.plan = plan
            user.subscription_tier = plan
            return "upgraded to scale"
        return "already active"

    period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
    if subscription is None:
        db.add(
            Subscription(
                user_id=user.id,
                plan=plan,
                status=SubscriptionStatus.ACTIVE.value,
                provider=PAYMENT_PROVIDER_MOCK,
                current_period_start=now,
                current_period_end=period_end,
                cancel_at_period_end=False,
            )
        )
    else:
        subscription.plan = plan
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.provider = PAYMENT_PROVIDER_MOCK
        subscription.current_period_start = now
        subscription.current_period_end = period_end
        subscription.cancel_at_period_end = False
    user.subscription_tier = plan
    return "activated scale plan"


async def grant(db: AsyncSession, email: str) -> bool:
    """Promote one account. Returns whether the account existed."""
    user = await db.scalar(sa.select(User).where(User.email == email))
    if user is None:
        logger.warning("No account for %s — register it first, then re-run.", email)
        return False

    now = datetime.now(UTC)
    user.role = UserRole.ADMIN.value
    user.email_verified = True
    sub_status = await _seed_scale_subscription(db, user, now=now)
    await db.commit()
    logger.info("Promoted %s to admin (%s).", email, sub_status)
    return True


async def _main(emails: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    resolved = _collect_emails(emails)
    if not resolved:
        logger.error(
            "No emails given. Pass --email you@example.com or set %s.", _ENV_EMAILS
        )
        return
    try:
        async with SessionLocal() as db:
            for email in resolved:
                await grant(db, email)
    finally:
        await close_connections()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote accounts to admin.")
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help="Email of an account to promote (repeatable).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(args.email))
