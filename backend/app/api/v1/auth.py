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
    VerifyEmailCodeRequest,
    VerifyEmailRequest,
)
from app.services import (
    auth_service,
    billing_service,
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

# One fixed message for both registration outcomes. A taken address and a free
# one must produce byte-identical responses, or the endpoint is an oracle.
_REGISTER_ACCEPTED = "Check your email — we've sent you the next step."

# Tighter limit on auth endpoints to slow credential stuffing and email
# bombing. Mostly unauthenticated (keyed by client IP); resend-verification
# carries a token and is keyed by user.
_auth_rate_limit = rate_limit(RATE_LIMIT_AUTH, scope="auth")


@router.post(
    "/register",
    response_model=DetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_auth_rate_limit],
)
async def register(payload: RegisterRequest, db: DbSession) -> DetailResponse:
    """Create a new user account.

    A fresh account is provisioned with an active FREE plan (unlimited tokens)
    and can start tasks immediately.

    Always 202 with a fixed body: a taken address must be indistinguishable
    from a free one, the same rule /forgot-password and /resend-verification
    already follow. A duplicate creates nothing and notifies the real owner
    instead.

    Known residual: an attacker can still probe by following this with a
    /login attempt, because registering a *free* address sets a password they
    know. Closing that needs login gated on verification, which the soft-gate
    design deliberately does not do.

    This does mean /register can mail a victim repeatedly. The bound is the
    per-IP _auth_rate_limit -- the same exposure /forgot-password carries by
    design.
    """
    email = payload.email.lower()
    # Build the user -- and so hash the password -- before the branch, so
    # Argon2 dominates both paths and the duplicate case is not measurably
    # faster. A pre-SELECT existence check would introduce exactly the timing
    # oracle this endpoint is closing.
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    try:
        # Flush to surface a duplicate email and to assign user.id before any
        # dependent row references it.
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Re-read rather than trusting the payload: guards the narrow race
        # where the row vanished between the violation and here.
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            await email_service.send_registration_attempt(existing.email)
        return DetailResponse(detail=_REGISTER_ACCEPTED)

    # Every account starts on the active FREE plan, in the same transaction as
    # the user row so the two can never diverge. This is also what keeps
    # usage_records writable: record_task_usage drops the record when there is
    # no subscription row to anchor period_start to.
    await billing_service.ensure_free_subscription(db, user)

    # Issue the token inside the same transaction as the user row; send only
    # after commit so an email can never precede (or roll back with) the data.
    raw_token, raw_code = await email_service.issue_token(
        db, user.id, EmailTokenPurpose.VERIFY_EMAIL, with_code=True
    )
    await db.commit()
    await email_service.send_verification(email, raw_token, raw_code)
    return DetailResponse(detail=_REGISTER_ACCEPTED)


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


async def _apply_email_change(db: DbSession, claimed) -> DetailResponse:  # noqa: ANN001
    """Move the account onto its confirmed address and lock out old sessions."""
    user, new_email = claimed.user, claimed.new_email
    user.email = new_email
    # Stays verified: clicking this link is exactly the proof that the new
    # inbox is reachable.
    user.email_verified = True
    try:
        # Flush before anything else touches the session: revoking sessions
        # issues a query, whose autoflush would raise this same IntegrityError
        # from outside any handler. Surfacing it here keeps it catchable.
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # The only place a collision can surface. By now the caller has proven
        # they can read that inbox, so this leaks nothing they could not learn
        # by trying to register it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That address is already in use by another account.",
        ) from exc
    # A changed sign-in address should not leave stale refresh tokens alive.
    await auth_service.revoke_other_families(db, user.id, keep_family=None)
    await db.commit()
    return DetailResponse(detail="Email address updated.")


@router.post(
    "/change-email",
    response_model=DetailResponse,
    dependencies=[_auth_rate_limit],
)
async def confirm_email_change(
    payload: VerifyEmailRequest, db: DbSession
) -> DetailResponse:
    """Redeem an email-change link. Public, like /verify-email: the link lands
    in a mail client that may not share the signed-in browser."""
    claimed = await email_service.consume_email_change(db, raw_token=payload.token)
    if claimed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This confirmation link is invalid or has expired.",
        )
    return await _apply_email_change(db, claimed)


@router.post(
    "/change-email/code",
    response_model=DetailResponse,
    dependencies=[rate_limit(RATE_LIMIT_EMAIL_CODE, scope="email_code")],
)
async def confirm_email_change_code(
    payload: VerifyEmailCodeRequest, user: CurrentUser, db: DbSession
) -> DetailResponse:
    """Redeem the numeric code from an email-change confirmation.

    Authenticated for the same reason as /verify-email/code: six digits are
    only unique within one account's rows.
    """
    claimed = await email_service.consume_email_change(
        db, user_id=user.id, raw_code=payload.code
    )
    if claimed is None:
        await db.commit()  # persist the spent attempt
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code is invalid or has expired.",
        )
    return await _apply_email_change(db, claimed)


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
