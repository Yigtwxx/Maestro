"""Transactional email flows: single-use tokens plus fire-and-forget sending.

Token rows store only a SHA-256 hash; the plaintext exists solely in the
emailed link. ``issue_token``/``consume_token`` leave committing to the
caller so they compose with endpoint transactions. The ``send_*`` helpers
never raise: a provider failure is logged and the calling endpoint proceeds
(an email outage must not block registration or account deletion).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    EMAIL_TOKEN_BYTES,
    EMAIL_VERIFY_TOKEN_TTL_HOURS,
    PASSWORD_RESET_TOKEN_TTL_MINUTES,
    RESET_PASSWORD_PATH,
    VERIFY_EMAIL_PATH,
    EmailTokenPurpose,
)
from app.models.email_token import EmailToken
from app.models.user import User
from app.services.email import EmailMessage, get_email_provider, templates

logger = logging.getLogger(__name__)

_TOKEN_TTLS: dict[EmailTokenPurpose, timedelta] = {
    EmailTokenPurpose.VERIFY_EMAIL: timedelta(hours=EMAIL_VERIFY_TOKEN_TTL_HOURS),
    EmailTokenPurpose.RESET_PASSWORD: timedelta(
        minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES
    ),
}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_token(
    db: AsyncSession, user_id: uuid.UUID, purpose: EmailTokenPurpose
) -> str:
    """Create a fresh token and return its plaintext. Caller commits.

    Prior unused tokens of the same purpose are invalidated so only the most
    recently emailed link works.
    """
    now = datetime.now(UTC)
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose.value,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
        # Bulk DML: skip the ORM evaluate pass (naive-vs-aware compare on
        # SQLite), same as auth_service.revoke_family.
        .execution_options(synchronize_session=False)
    )
    raw = secrets.token_urlsafe(EMAIL_TOKEN_BYTES)
    db.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose.value,
            token_hash=_hash_token(raw),
            expires_at=now + _TOKEN_TTLS[purpose],
        )
    )
    return raw


async def consume_token(
    db: AsyncSession, raw_token: str, purpose: EmailTokenPurpose
) -> User | None:
    """Redeem a token: mark it used and return its owner. Caller commits.

    Returns None for unknown, already-used, wrong-purpose or expired tokens --
    indistinguishable on purpose, so responses cannot leak token state.

    The claim is a single conditional UPDATE, never a read-then-write: two
    concurrent redemptions of the same link must not both succeed. Expiry is
    part of the same predicate; SQLite stores DateTime(timezone=True) as UTC
    wall-clock text, so the tz-aware bound parameter compares correctly there
    as well as against a PostgreSQL timestamptz.
    """
    now = datetime.now(UTC)
    user_id = await db.scalar(
        update(EmailToken)
        .where(
            EmailToken.token_hash == _hash_token(raw_token),
            EmailToken.purpose == purpose.value,
            EmailToken.used_at.is_(None),
            EmailToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(EmailToken.user_id)
        # Bulk DML: skip the ORM evaluate pass (naive-vs-aware compare on
        # SQLite), same as issue_token above.
        .execution_options(synchronize_session=False)
    )
    if user_id is None:
        return None
    return await db.get(User, user_id)


def _action_link(path: str, raw_token: str) -> str:
    return f"{settings.site_url.rstrip('/')}{path}?token={raw_token}"


async def _send_safely(to: str, subject: str, html: str, text: str) -> None:
    """Deliver one message; log (never propagate) provider failures."""
    try:
        await get_email_provider().send(
            EmailMessage(to=to, subject=subject, html=html, text=text)
        )
    except Exception as exc:  # noqa: BLE001 - the failure policy is "never raise"
        # The recipient address is PII and the body carries a live token, and a
        # provider's exception text could echo either -- log only the subject
        # and the exception class, never the traceback.
        logger.error(
            "email send failed (subject=%r, error=%s)", subject, type(exc).__name__
        )


async def send_verification(to: str, raw_token: str) -> None:
    subject, html, text = templates.verification_email(
        _action_link(VERIFY_EMAIL_PATH, raw_token)
    )
    await _send_safely(to, subject, html, text)


async def send_password_reset(to: str, raw_token: str) -> None:
    subject, html, text = templates.password_reset_email(
        _action_link(RESET_PASSWORD_PATH, raw_token)
    )
    await _send_safely(to, subject, html, text)


async def send_deletion_requested(to: str, purge_after: datetime) -> None:
    subject, html, text = templates.deletion_requested_email(
        purge_after.date().isoformat()
    )
    await _send_safely(to, subject, html, text)


async def send_deletion_cancelled(to: str) -> None:
    subject, html, text = templates.deletion_cancelled_email()
    await _send_safely(to, subject, html, text)
