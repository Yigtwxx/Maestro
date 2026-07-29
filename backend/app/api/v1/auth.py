"""Authentication endpoints: register, login (+ TOTP step), refresh, logout."""

from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    MFA_TOKEN_EXPIRE_MINUTES,
    RATE_LIMIT_AUTH,
    RATE_LIMIT_EMAIL_CODE,
    EmailTokenPurpose,
)
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    DetailResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResult,
    MfaChallenge,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    TotpVerifyRequest,
    UserPublic,
    VerifyEmailCodeRequest,
    VerifyEmailRequest,
)
from app.services import (
    auth_service,
    email_service,
    two_factor_service,
)
from app.utils.rate_limiter import rate_limit
from app.utils.request_context import client_ip, user_agent

_INVALID_MFA = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired verification session.",
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Tighter limit on auth endpoints to slow credential stuffing and email
# bombing. Mostly unauthenticated (keyed by client IP); resend-verification
# carries a token and is keyed by user.
_auth_rate_limit = rate_limit(RATE_LIMIT_AUTH, scope="auth")


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_auth_rate_limit],
)
async def register(payload: RegisterRequest, db: DbSession) -> User:
    """Create a new user account.

    There is no free plan and no trial: a fresh account holds no subscription
    and must subscribe to a paid plan before it can start any task.
    """
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    try:
        # Flush to surface a duplicate email and to assign user.id before any
        # dependent row references it.
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    # Issue the token inside the same transaction as the user row; send only
    # after commit so an email can never precede (or roll back with) the data.
    raw_token, raw_code = await email_service.issue_token(
        db, user.id, EmailTokenPurpose.VERIFY_EMAIL, with_code=True
    )
    await db.commit()
    await db.refresh(user)
    await email_service.send_verification(user.email, raw_token, raw_code)
    return user


@router.post("/login", response_model=LoginResult, dependencies=[_auth_rate_limit])
async def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResult:
    """Authenticate. Returns a token pair, or an MFA challenge when 2FA is on.

    Captures the User-Agent and client IP so the session shows up recognisably
    under the profile's Active Sessions.
    """
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if user.totp_enabled:
        # Password OK, but a second factor is required. Hand out a short-lived
        # interim token that only /login/totp accepts (it is not an access token).
        mfa_token = create_token(
            str(user.id),
            "mfa",
            expires_delta=timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES),
        )
        return MfaChallenge(mfa_token=mfa_token)
    return await auth_service.issue_token_pair(
        db, user, user_agent=user_agent(request), ip_address=client_ip(request)
    )


@router.post("/login/totp", response_model=TokenPair, dependencies=[_auth_rate_limit])
async def login_totp(
    payload: TotpVerifyRequest, request: Request, db: DbSession
) -> TokenPair:
    """Complete a 2FA login: verify a TOTP (or recovery) code, issue tokens."""
    try:
        claims = decode_token(payload.mfa_token, expected_type="mfa")
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise _INVALID_MFA from exc

    user = await db.get(User, user_id)
    if user is None or not user.totp_enabled:
        raise _INVALID_MFA
    if not await two_factor_service.verify_login(db, user, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authentication code.",
        )
    return await auth_service.issue_token_pair(
        db, user, user_agent=user_agent(request), ip_address=client_ip(request)
    )


@router.post("/refresh", response_model=TokenPair, dependencies=[_auth_rate_limit])
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Exchange a refresh token for a new pair, rotating (invalidating) the old.

    Replaying an already-rotated token revokes the whole session family — the
    reuse-detection defence against a stolen refresh token.
    """
    return await auth_service.rotate_refresh_token(db, payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_auth_rate_limit],
)
async def logout(payload: RefreshRequest, db: DbSession) -> Response:
    """Revoke the session family behind a refresh token. Idempotent."""
    await auth_service.logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verify-email",
    response_model=DetailResponse,
    dependencies=[_auth_rate_limit],
)
async def verify_email(payload: VerifyEmailRequest, db: DbSession) -> DetailResponse:
    """Redeem an emailed verification token. Public: the user who clicks the
    link may not be signed in on that browser."""
    user = await email_service.consume_token(
        db, payload.token, EmailTokenPurpose.VERIFY_EMAIL
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )
    user.email_verified = True
    await db.commit()
    return DetailResponse(detail="Email verified.")


@router.post(
    "/verify-email/code",
    response_model=DetailResponse,
    dependencies=[rate_limit(RATE_LIMIT_EMAIL_CODE, scope="email_code")],
)
async def verify_email_code(
    payload: VerifyEmailCodeRequest, user: CurrentUser, db: DbSession
) -> DetailResponse:
    """Redeem the numeric code from a verification email.

    Authenticated, unlike the link route: six digits are not unique, so the
    code can only be looked up within one account's rows. An already-verified
    caller gets the same 200 without spending an attempt.
    """
    if user.email_verified:
        return DetailResponse(detail="Email verified.")
    verified = await email_service.consume_code(
        db, user.id, payload.code, EmailTokenPurpose.VERIFY_EMAIL
    )
    await db.commit()
    if verified is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code is invalid or has expired.",
        )
    verified.email_verified = True
    await db.commit()
    return DetailResponse(detail="Email verified.")


@router.post(
    "/resend-verification",
    response_model=DetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_auth_rate_limit],
)
async def resend_verification(user: CurrentUser, db: DbSession) -> DetailResponse:
    """Rotate the verification token and re-send the email.

    A verified account gets the same 202 without an email, so the response
    never reveals verification state.
    """
    if not user.email_verified:
        raw_token, raw_code = await email_service.issue_token(
            db, user.id, EmailTokenPurpose.VERIFY_EMAIL, with_code=True
        )
        await db.commit()
        await email_service.send_verification(user.email, raw_token, raw_code)
    return DetailResponse(
        detail="If your email is unverified, a new link is on its way."
    )


@router.post(
    "/forgot-password",
    response_model=DetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_auth_rate_limit],
)
async def forgot_password(
    payload: ForgotPasswordRequest, db: DbSession
) -> DetailResponse:
    """Start a password reset. Always 202: the response must not reveal
    whether an account exists (enumeration resistance).

    Works for deletion-locked accounts too -- they keep working credentials
    during the grace period by design, so they must be able to recover them.
    """
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        # Link only, no code: a reset grants account takeover, so it keeps the
        # 256-bit token as its single credential rather than gaining a
        # six-digit one.
        raw_token, _ = await email_service.issue_token(
            db, user.id, EmailTokenPurpose.RESET_PASSWORD
        )
        await db.commit()
        await email_service.send_password_reset(user.email, raw_token)
    return DetailResponse(
        detail="If an account exists for that address, a reset link is on its way."
    )


@router.post(
    "/reset-password",
    response_model=DetailResponse,
    dependencies=[_auth_rate_limit],
)
async def reset_password(
    payload: ResetPasswordRequest, db: DbSession
) -> DetailResponse:
    """Redeem a reset token and set a new password.

    A reset usually means the old password (or inbox) was compromised, so
    every existing session is revoked; the user signs in fresh.
    """
    user = await email_service.consume_token(
        db, payload.token, EmailTokenPurpose.RESET_PASSWORD
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    user.hashed_password = hash_password(payload.new_password)
    await auth_service.revoke_other_families(db, user.id, keep_family=None)
    await db.commit()
    return DetailResponse(detail="Password updated. You can sign in now.")
