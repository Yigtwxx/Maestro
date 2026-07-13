"""Shared FastAPI dependencies (auth, current user)."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import UserRole
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=True)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_access_payload(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Decode and validate the Bearer access token once per request.

    FastAPI caches a dependency's result within a single request, so both the
    current-user and session-family dependencies share this one decode instead
    of verifying the JWT twice on every authenticated call.
    """
    try:
        return decode_token(credentials.credentials, expected_type="access")
    except jwt.InvalidTokenError as exc:
        raise _CREDENTIALS_EXC from exc


async def get_current_user(
    payload: Annotated[dict, Depends(get_access_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from a Bearer access token."""
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = await db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_session_family(
    payload: Annotated[dict, Depends(get_access_payload)],
) -> uuid.UUID | None:
    """The ``fam`` (session family) claim of the access token, if present.

    Lets a request identify *its own* session for listing/"sign out others".
    Returns None for tokens minted before the claim existed, so callers must
    treat None as "unknown current session", never as "no sessions". The token
    itself is already validated by :func:`get_access_payload`.
    """
    fam = payload.get("fam")
    try:
        return uuid.UUID(fam) if fam else None
    except ValueError:
        return None


CurrentFamily = Annotated[uuid.UUID | None, Depends(get_current_session_family)]


async def get_active_user(user: CurrentUser) -> User:
    """Resolve the authenticated user, rejecting accounts pending deletion.

    A locked account keeps working credentials on purpose: the user must be able
    to sign in to restore it or export their data during the grace period. Only
    the product surface is closed, via this dependency. The allow-list that stays
    on ``CurrentUser`` is: read profile, request deletion, cancel deletion,
    export data.

    A moderator-applied suspension is enforced at the same point but is *not*
    user-cancelable: the account keeps working credentials (so a suspended user
    can still read their profile and export data) yet the product surface stays
    closed until a moderator lifts the flag.
    """
    if user.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is scheduled for deletion. Restore it to continue.",
        )
    if user.suspended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact support for details.",
        )
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


async def get_admin_user(user: ActiveUser) -> User:
    """An active user with the ``admin`` role (the moderation surface gate).

    The role is read fresh off the user row each request rather than from a JWT
    claim, so revoking admin takes effect immediately instead of lingering for
    the access token's lifetime. Layered on ``ActiveUser``, so a suspended or
    deletion-locked admin is refused here too.
    """
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


async def get_verified_user(user: ActiveUser) -> User:
    """An active user whose email address is verified (soft gate).

    Applied only to abuse-sensitive writes -- task start and BYOK key
    creation -- so onboarding stays friction-free. Self-hosted deployments may
    disable the gate via EMAIL_VERIFICATION_REQUIRED=false; verification
    emails still go out either way. Admins bypass the gate (staff accounts).
    """
    if user.role == UserRole.ADMIN.value:
        return user
    if settings.email_verification_required and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address to use this feature.",
        )
    return user


VerifiedUser = Annotated[User, Depends(get_verified_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
