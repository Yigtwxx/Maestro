"""Authentication endpoints: register, login, refresh (JWT)."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.constants import RATE_LIMIT_AUTH
from app.core.deps import DbSession
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.services import billing_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# Tighter limit on auth endpoints to slow credential stuffing. Every route here
# is unauthenticated, so the bucket is keyed by client IP.
_auth_rate_limit = rate_limit(RATE_LIMIT_AUTH, scope="auth")


def _issue_tokens(user: User) -> TokenPair:
    subject = str(user.id)
    return TokenPair(
        access_token=create_token(subject, "access"),
        refresh_token=create_token(subject, "refresh"),
    )


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_auth_rate_limit],
)
async def register(payload: RegisterRequest, db: DbSession) -> User:
    """Create a new user account, on a Starter-quota trial.

    There is no free plan: the trial is what makes a fresh account usable, and
    once it lapses the user must subscribe before starting tasks.
    """
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    try:
        # Flush to surface a duplicate email and to assign user.id before the
        # subscription row references it.
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    await billing_service.start_trial(db, user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair, dependencies=[_auth_rate_limit])
async def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    """Authenticate and return an access/refresh token pair."""
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenPair, dependencies=[_auth_rate_limit])
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Exchange a valid refresh token for a new token pair."""
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
        user = await db.get(User, uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    return _issue_tokens(user)
