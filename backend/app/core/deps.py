"""Shared FastAPI dependencies (auth, current user)."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=True)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from a Bearer access token."""
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = await db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_active_user(user: CurrentUser) -> User:
    """Resolve the authenticated user, rejecting accounts pending deletion.

    A locked account keeps working credentials on purpose: the user must be able
    to sign in to restore it or export their data during the grace period. Only
    the product surface is closed, via this dependency. The allow-list that stays
    on ``CurrentUser`` is: read profile, request deletion, cancel deletion,
    export data.
    """
    if user.deletion_requested_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is scheduled for deletion. Restore it to continue.",
        )
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
