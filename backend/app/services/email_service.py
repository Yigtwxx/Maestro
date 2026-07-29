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
from typing import NamedTuple

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    CHANGE_EMAIL_PATH,
    EMAIL_CHANGE_TOKEN_TTL_HOURS,
    EMAIL_CODE_DIGITS,
    EMAIL_CODE_MAX_ATTEMPTS,
    EMAIL_CODE_TTL_MINUTES,
    EMAIL_TOKEN_BYTES,
    EMAIL_VERIFY_TOKEN_TTL_HOURS,
    FORGOT_PASSWORD_PATH,
    LOGIN_PATH,
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
    EmailTokenPurpose.CHANGE_EMAIL: timedelta(hours=EMAIL_CHANGE_TOKEN_TTL_HOURS),
}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    """A zero-padded numeric code. ``secrets``, never ``random``."""
    return f"{secrets.randbelow(10**EMAIL_CODE_DIGITS):0{EMAIL_CODE_DIGITS}d}"


async def issue_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: EmailTokenPurpose,
    *,
    with_code: bool = False,
    new_email: str | None = None,
) -> tuple[str, str | None]:
    """Create a fresh token and return its plaintext. Caller commits.

    Prior unused tokens of the same purpose are invalidated so only the most
    recently emailed link works.

    ``with_code`` additionally mints a short numeric code for the same row,
    returned as the second element. The code expires far sooner than the link
    (see EMAIL_CODE_TTL_MINUTES) because six digits is a guessable keyspace.

    ``new_email`` records the address a CHANGE_EMAIL token would move the
    account to, binding the token to that address for its whole life.
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
    raw_code = _generate_code() if with_code else None
    db.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose.value,
            token_hash=_hash_token(raw),
            expires_at=now + _TOKEN_TTLS[purpose],
            code_hash=_hash_token(raw_code) if raw_code is not None else None,
            code_expires_at=(
                now + timedelta(minutes=EMAIL_CODE_TTL_MINUTES)
                if raw_code is not None
                else None
            ),
            new_email=new_email,
        )
    )
    return raw, raw_code


class ClaimedToken(NamedTuple):
    """A redeemed row's payload: its owner, plus whatever it carried."""

    user: User
    new_email: str | None


async def _claim_by_token(
    db: AsyncSession, raw_token: str, purpose: EmailTokenPurpose
) -> ClaimedToken | None:
    """Mark a token used and hand back its row. Caller commits.

    The claim is a single conditional UPDATE, never a read-then-write: two
    concurrent redemptions of the same link must not both succeed. Expiry is
    part of the same predicate; SQLite stores DateTime(timezone=True) as UTC
    wall-clock text, so the tz-aware bound parameter compares correctly there
    as well as against a PostgreSQL timestamptz.
    """
    now = datetime.now(UTC)
    row = (
        await db.execute(
            update(EmailToken)
            .where(
                EmailToken.token_hash == _hash_token(raw_token),
                EmailToken.purpose == purpose.value,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(EmailToken.user_id, EmailToken.new_email)
            # Bulk DML: skip the ORM evaluate pass (naive-vs-aware compare on
            # SQLite), same as issue_token above.
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        return None
    user = await db.get(User, row.user_id)
    return None if user is None else ClaimedToken(user, row.new_email)


async def _claim_by_code(
    db: AsyncSession, user_id: uuid.UUID, raw_code: str, purpose: EmailTokenPurpose
) -> ClaimedToken | None:
    """Mark a code used and hand back its row. Caller commits.

    Scoped to ``user_id`` on purpose: six digits are nowhere near unique, so a
    code can only ever be looked up inside one account's rows. That is why the
    code endpoints require authentication while the link endpoint does not --
    a 256-bit token is globally unique on its own, a code is not.

    A failed attempt burns one of EMAIL_CODE_MAX_ATTEMPTS; once they are gone
    the row can never be claimed again and the user must request a new code.
    """
    now = datetime.now(UTC)
    row = (
        await db.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == user_id,
                EmailToken.purpose == purpose.value,
                EmailToken.used_at.is_(None),
                EmailToken.code_hash == _hash_token(raw_code),
                EmailToken.code_expires_at > now,
                EmailToken.code_attempts < EMAIL_CODE_MAX_ATTEMPTS,
            )
            .values(used_at=now)
            .returning(EmailToken.user_id, EmailToken.new_email)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is not None:
        user = await db.get(User, row.user_id)
        return None if user is None else ClaimedToken(user, row.new_email)

    # Wrong or unusable code: spend an attempt on whatever live row this user
    # has, so repeated guessing exhausts the cap instead of running forever.
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose.value,
            EmailToken.used_at.is_(None),
            EmailToken.code_hash.is_not(None),
        )
        .values(code_attempts=EmailToken.code_attempts + 1)
        .execution_options(synchronize_session=False)
    )
    return None


async def consume_token(
    db: AsyncSession, raw_token: str, purpose: EmailTokenPurpose
) -> User | None:
    """Redeem a token: mark it used and return its owner. Caller commits.

    Returns None for unknown, already-used, wrong-purpose or expired tokens --
    indistinguishable on purpose, so responses cannot leak token state.
    """
    claimed = await _claim_by_token(db, raw_token, purpose)
    return None if claimed is None else claimed.user


async def consume_code(
    db: AsyncSession, user_id: uuid.UUID, raw_code: str, purpose: EmailTokenPurpose
) -> User | None:
    """Redeem a numeric code for one user. Caller commits.

    Returns None for a wrong, expired, capped or missing code, all
    indistinguishable, same rule as ``consume_token``.
    """
    claimed = await _claim_by_code(db, user_id, raw_code, purpose)
    return None if claimed is None else claimed.user


async def consume_email_change(
    db: AsyncSession,
    *,
    raw_token: str | None = None,
    user_id: uuid.UUID | None = None,
    raw_code: str | None = None,
) -> ClaimedToken | None:
    """Redeem an email-change token or code, keeping the pending address.

    Returns None unless the claim succeeded *and* carried a ``new_email``: a
    CHANGE_EMAIL row without one would be a bug, and applying an empty address
    would lock the account out of its own recovery.
    """
    if raw_token is not None:
        claimed = await _claim_by_token(db, raw_token, EmailTokenPurpose.CHANGE_EMAIL)
    elif user_id is not None and raw_code is not None:
        claimed = await _claim_by_code(
            db, user_id, raw_code, EmailTokenPurpose.CHANGE_EMAIL
        )
    else:  # pragma: no cover - guarded by the two call sites
        raise ValueError("consume_email_change needs a token or a user_id + code")
    if claimed is None or not claimed.new_email:
        return None
    return claimed


def _site_link(path: str) -> str:
    return f"{settings.site_url.rstrip('/')}{path}"


def _action_link(path: str, raw_token: str) -> str:
    return f"{_site_link(path)}?token={raw_token}"


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


async def send_verification(
    to: str, raw_token: str, raw_code: str | None = None
) -> None:
    subject, html, text = templates.verification_email(
        _action_link(VERIFY_EMAIL_PATH, raw_token), raw_code
    )
    await _send_safely(to, subject, html, text)


async def send_registration_attempt(to: str) -> None:
    """Tell an existing account that someone tried to register its address.

    Carries no token and no code: whoever triggered this is not necessarily
    the owner, so the mail must be informational only.
    """
    subject, html, text = templates.registration_attempt_email(
        _site_link(LOGIN_PATH), _site_link(FORGOT_PASSWORD_PATH)
    )
    await _send_safely(to, subject, html, text)


async def send_email_change_verification(
    to: str, raw_token: str, raw_code: str | None = None
) -> None:
    """To the new address: the link (and code) that actually applies the change."""
    subject, html, text = templates.email_change_verification(
        _action_link(CHANGE_EMAIL_PATH, raw_token), raw_code
    )
    await _send_safely(to, subject, html, text)


async def send_email_change_notice(to: str, new_email: str) -> None:
    """To the old address: a heads-up carrying no token and no code."""
    subject, html, text = templates.email_change_notice(new_email)
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
