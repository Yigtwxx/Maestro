"""Refresh-token rotation, reuse-detection, and revocation.

Refresh tokens are single-use: every ``/refresh`` rotates the presented token
(revokes it, issues a successor in the same ``family_id``). Replaying an already
revoked token is a theft signal — the whole family is revoked so both the thief
and the victim are logged out (OAuth Security BCP). State lives in Postgres
(``refresh_tokens``), the durable source of truth; access tokens stay stateless.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenPair
from app.utils.timeseries import as_utc

_INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token."
)


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Mint an access/refresh pair and record the refresh token server-side.

    A fresh ``family_id`` starts a new session (login); passing one continues an
    existing lineage (rotation). ``user_agent``/``ip_address`` are the login
    context, stored so the user can recognise their sessions. The access token
    also carries the ``fam`` claim so the current session can identify itself
    (session listing, "sign out other devices"). Commits before returning.
    """
    now = datetime.now(UTC)
    family = family_id or uuid.uuid4()
    jti = uuid.uuid4()
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    subject = str(user.id)

    access_token = create_token(subject, "access", extra_claims={"fam": str(family)})
    refresh_token = create_token(
        subject, "refresh", extra_claims={"jti": str(jti), "fam": str(family)}
    )
    db.add(
        RefreshToken(
            id=jti,
            user_id=user.id,
            family_id=family,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            last_used_at=now,
        )
    )
    await db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    """Revoke every still-active token in a session family (no commit)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
        # Bulk DML: skip the ORM evaluate pass (it can't compare SQLite's naive
        # timestamps to tz-aware values). We commit right after, so in-session
        # object state does not matter here.
        .execution_options(synchronize_session=False)
    )


async def list_active_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """One summary row per active (non-revoked, non-expired) session family.

    Login context is constant within a family (carried forward on rotation), so
    ``max`` collapses each family to its single identity; ``min(created_at)`` is
    the login time and ``max(last_used_at)`` the most recent activity.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(
            RefreshToken.family_id,
            func.min(RefreshToken.created_at).label("created_at"),
            func.max(RefreshToken.last_used_at).label("last_used_at"),
            func.max(RefreshToken.user_agent).label("user_agent"),
            func.max(RefreshToken.ip_address).label("ip_address"),
        )
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .group_by(RefreshToken.family_id)
    )
    return [
        {
            "family_id": row.family_id,
            "created_at": row.created_at,
            "last_used_at": row.last_used_at,
            "user_agent": row.user_agent,
            "ip_address": row.ip_address,
        }
        for row in result.all()
    ]


async def family_belongs_to_user(
    db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID
) -> bool:
    """Whether any refresh-token row ties this family to this user (ownership)."""
    result = await db.execute(
        select(RefreshToken.id)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.family_id == family_id,
        )
        .limit(1)
    )
    return result.first() is not None


async def revoke_other_families(
    db: AsyncSession, user_id: uuid.UUID, keep_family: uuid.UUID | None
) -> None:
    """Revoke all of a user's active sessions except ``keep_family`` (no commit).

    ``keep_family`` None revokes every session (e.g. no current family known).
    """
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if keep_family is not None:
        stmt = stmt.where(RefreshToken.family_id != keep_family)
    await db.execute(
        stmt.values(revoked_at=datetime.now(UTC)).execution_options(
            synchronize_session=False
        )
    )


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> TokenPair:
    """Exchange a valid refresh token for a new pair, rotating the old one.

    Raises 401 on any invalid/expired/unknown token. If an already-revoked token
    is replayed, the entire family is revoked before rejecting.
    """
    try:
        claims = decode_token(refresh_token, expected_type="refresh")
        jti = uuid.UUID(claims["jti"])
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise _INVALID_REFRESH from exc

    record = await db.get(RefreshToken, jti)
    if record is None:
        # Unknown/forged jti, or a stateless token issued before rotation existed.
        raise _INVALID_REFRESH

    if record.revoked_at is not None:
        # Replay of a rotated token → treat as theft and burn the whole family.
        await revoke_family(db, record.family_id)
        await db.commit()
        raise _INVALID_REFRESH

    now = datetime.now(UTC)
    if as_utc(record.expires_at) <= now:
        raise _INVALID_REFRESH

    user = await db.get(User, user_id)
    if user is None:
        raise _INVALID_REFRESH

    record.revoked_at = now
    await _delete_expired(db, user.id, now)
    # issue_token_pair commits, flushing the revoke + cleanup atomically with it.
    # Carry the session's login context forward so the family keeps one identity.
    return await issue_token_pair(
        db,
        user,
        family_id=record.family_id,
        user_agent=record.user_agent,
        ip_address=record.ip_address,
    )


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revoke the session family behind a refresh token. Idempotent.

    A malformed/expired token is a no-op: logout must not leak token validity.
    """
    try:
        claims = decode_token(refresh_token, expected_type="refresh")
        family_id = uuid.UUID(claims["fam"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return
    await revoke_family(db, family_id)
    await db.commit()


async def _delete_expired(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    """Opportunistically prune a user's expired rows so the table stays bounded."""
    await db.execute(
        delete(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.expires_at <= now)
        # See revoke_family: bypass the ORM evaluate pass (naive-vs-aware compare).
        .execution_options(synchronize_session=False)
    )
