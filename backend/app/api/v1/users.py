"""Current-user profile endpoints: read/update profile, password, deletion.

Subscription changes live in ``api/v1/billing.py``.

Deletion is a two-phase, reversible flow (GDPR Art.17 / KVKK Art.7): requesting
it locks the account and schedules a purge ``ACCOUNT_DELETION_GRACE_DAYS`` later;
the purge itself is carried out by ``app.scripts.purge_deleted_accounts``.

The four endpoints reachable while locked -- read profile, request deletion,
cancel deletion, export data -- keep ``CurrentUser``. Everything else on this
router takes ``ActiveUser`` and 403s for a locked account.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    ACCOUNT_DELETION_GRACE_DAYS,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
    LLMProvider,
    SubscriptionStatus,
)
from app.core.deps import ActiveUser, CurrentFamily, CurrentUser, DbSession
from app.core.security import hash_password, verify_password
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.user import (
    AccountDelete,
    AccountDeletionStatus,
    PasswordChange,
    RecoveryCodes,
    SessionInfo,
    TwoFactorDisable,
    TwoFactorEnable,
    TwoFactorSetup,
    UserUpdate,
)
from app.services import (
    auth_service,
    billing_service,
    email_service,
    two_factor_service,
    user_service,
)
from app.utils.rate_limiter import rate_limit
from app.utils.request_context import summarize_user_agent

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST

# Session-management endpoints keep the *current* session and revoke the rest,
# which requires knowing which family is current. A token minted before the
# ``fam`` claim existed can't identify it; refuse rather than silently revoke
# every session (including the caller's own). Re-login mints a token with ``fam``.
_REAUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Please sign in again to manage your sessions.",
)

router = APIRouter(prefix="/users", tags=["users"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="users")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="users")


def _deletion_status(requested_at: datetime) -> AccountDeletionStatus:
    """Derive the purge date from the request timestamp."""
    return AccountDeletionStatus(
        deletion_requested_at=requested_at,
        purge_after=requested_at + timedelta(days=ACCOUNT_DELETION_GRACE_DAYS),
    )


async def _has_active_key(
    db: DbSession, user_id: uuid.UUID, provider: LLMProvider
) -> bool:
    """Whether the user has an active BYOK key for the given provider."""
    result = await db.execute(
        select(ApiKey.id).where(
            ApiKey.user_id == user_id,
            ApiKey.provider == provider.value,
            ApiKey.is_active.is_(True),
        )
    )
    return result.first() is not None


@router.get("/me", response_model=UserPublic, dependencies=[_read_rate_limit])
async def get_me(user: CurrentUser) -> User:
    """Return the current user's profile."""
    return user


@router.patch("/me", response_model=UserPublic, dependencies=[_write_rate_limit])
async def update_me(payload: UserUpdate, user: ActiveUser, db: DbSession) -> User:
    """Partially update the current user's profile.

    ``default_provider`` requires an active key for non-local providers so the
    default brain can always start a task (CLAUDE.md §9.1).
    """
    if "display_name" in payload.model_fields_set:
        user.display_name = payload.display_name
    if "email" in payload.model_fields_set and payload.email is not None:
        user.email = payload.email.lower()
    if "bio" in payload.model_fields_set:
        user.bio = payload.bio
    if "avatar_color" in payload.model_fields_set:
        user.avatar_color = payload.avatar_color
    if "avatar_emoji" in payload.model_fields_set:
        user.avatar_emoji = payload.avatar_emoji
    if "timezone" in payload.model_fields_set:
        user.timezone = payload.timezone
    if (
        "default_reviewer_enabled" in payload.model_fields_set
        and payload.default_reviewer_enabled is not None
    ):
        user.default_reviewer_enabled = payload.default_reviewer_enabled
    if "default_provider" in payload.model_fields_set:
        provider = payload.default_provider
        if (
            provider is not None
            and provider is not LLMProvider.OLLAMA
            and not await _has_active_key(db, user.id, provider)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot set '{provider.value}' as the default brain: "
                    "no active API key. Please connect one first."
                ),
            )
        user.default_provider = provider.value if provider is not None else None
    if "model_preferences" in payload.model_fields_set:
        # Whole-map replace; reassignment (never in-place mutation) so the
        # JSON column change is tracked by SQLAlchemy.
        user.model_preferences = payload.model_preferences
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    await db.refresh(user)
    return user


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def change_password(
    payload: PasswordChange,
    user: ActiveUser,
    current_family: CurrentFamily,
    db: DbSession,
) -> None:
    """Change the current user's password (requires the current one).

    Unless opted out, every *other* session is revoked: a password change should
    lock out anyone holding an old refresh token. The current session is kept so
    the user is not logged out of the device they just used.
    """
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.hashed_password = hash_password(payload.new_password)
    if payload.revoke_other_sessions:
        if current_family is None:
            raise _REAUTH_REQUIRED
        await auth_service.revoke_other_families(db, user.id, current_family)
    await db.commit()


@router.get(
    "/me/sessions",
    response_model=list[SessionInfo],
    dependencies=[_read_rate_limit],
)
async def list_sessions(
    user: ActiveUser, current_family: CurrentFamily, db: DbSession
) -> list[SessionInfo]:
    """List the user's active login sessions (one per refresh-token family)."""
    sessions = await auth_service.list_active_sessions(db, user.id)
    return [
        SessionInfo(
            id=s["family_id"],
            device=summarize_user_agent(s["user_agent"]),
            ip=s["ip_address"],
            created_at=s["created_at"],
            last_used_at=s["last_used_at"],
            current=s["family_id"] == current_family,
        )
        for s in sessions
    ]


@router.delete(
    "/me/sessions/{family_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def revoke_session(family_id: uuid.UUID, user: ActiveUser, db: DbSession) -> None:
    """Revoke a single session by family id. 404 if it is not the user's own."""
    if not await auth_service.family_belongs_to_user(db, user.id, family_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found."
        )
    await auth_service.revoke_family(db, family_id)
    await db.commit()


@router.post(
    "/me/sessions/revoke-others",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def revoke_other_sessions(
    user: ActiveUser, current_family: CurrentFamily, db: DbSession
) -> None:
    """Sign out of every session except the one making this request."""
    if current_family is None:
        raise _REAUTH_REQUIRED
    await auth_service.revoke_other_families(db, user.id, current_family)
    await db.commit()


@router.post(
    "/me/2fa/setup", response_model=TwoFactorSetup, dependencies=[_write_rate_limit]
)
async def setup_two_factor(user: ActiveUser, db: DbSession) -> TwoFactorSetup:
    """Begin TOTP enrollment: store a pending secret, return the QR to scan.

    Nothing is enforced until :func:`enable_two_factor` confirms a code, so this
    is safe without re-auth. Blocked while 2FA is already on (disable to re-key).
    """
    if user.totp_enabled:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="Two-factor auth is already enabled. Disable it first to re-key.",
        )
    secret, uri = await two_factor_service.begin_setup(db, user)
    return TwoFactorSetup(
        secret=secret, otpauth_uri=uri, qr_svg=two_factor_service.qr_svg(uri)
    )


@router.post(
    "/me/2fa/enable", response_model=RecoveryCodes, dependencies=[_write_rate_limit]
)
async def enable_two_factor(
    payload: TwoFactorEnable, user: ActiveUser, db: DbSession
) -> RecoveryCodes:
    """Confirm the pending secret with a code + password; return recovery codes."""
    if user.totp_enabled:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="Two-factor auth is already enabled."
        )
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=_BAD_REQUEST, detail="Password is incorrect.")
    try:
        codes = await two_factor_service.enable(db, user, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc
    return RecoveryCodes(recovery_codes=codes)


@router.post(
    "/me/2fa/disable", response_model=UserPublic, dependencies=[_write_rate_limit]
)
async def disable_two_factor(
    payload: TwoFactorDisable, user: ActiveUser, db: DbSession
) -> User:
    """Turn 2FA off. Requires the password; an optional code adds assurance."""
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=_BAD_REQUEST, detail="Password is incorrect.")
    if user.totp_enabled and payload.code:
        if not await two_factor_service.verify_login(db, user, payload.code):
            raise HTTPException(
                status_code=_BAD_REQUEST, detail="Invalid authentication code."
            )
    await two_factor_service.disable(db, user)
    await db.refresh(user)
    return user


@router.delete(
    "/me", response_model=AccountDeletionStatus, dependencies=[_write_rate_limit]
)
async def request_deletion(
    payload: AccountDelete, user: CurrentUser, db: DbSession
) -> AccountDeletionStatus:
    """Request account deletion: lock the account and start the grace period.

    Nothing is destroyed here. The account is locked out of the product
    immediately and purged only once the grace period lapses; until then the user
    may restore it. Idempotent -- re-requesting returns the original schedule
    rather than sliding the purge date forward.
    """
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is incorrect.",
        )
    if user.deletion_requested_at is not None:
        return _deletion_status(user.deletion_requested_at)

    user.deletion_requested_at = datetime.now(UTC)
    # Stop billing a user who can no longer use the product. Only an active paid
    # subscription is cancelled. Restoring does not resurrect a cancelled plan --
    # the user resubscribes.
    subscription = await billing_service.get_subscription(db, user.id)
    if (
        subscription is not None
        and SubscriptionStatus(subscription.status) is SubscriptionStatus.ACTIVE
    ):
        await billing_service.cancel(db, user)
    await db.commit()
    await db.refresh(user)
    deletion = _deletion_status(user.deletion_requested_at)
    # Confirmation is a courtesy, not part of the transaction: sent after
    # commit and never allowed to fail the request.
    await email_service.send_deletion_requested(user.email, deletion.purge_after)
    return deletion


@router.post(
    "/me/deletion/cancel", response_model=UserPublic, dependencies=[_write_rate_limit]
)
async def cancel_deletion(user: CurrentUser, db: DbSession) -> User:
    """Restore an account scheduled for deletion. Idempotent when not locked."""
    was_locked = user.deletion_requested_at is not None
    user.deletion_requested_at = None
    await db.commit()
    await db.refresh(user)
    if was_locked:
        await email_service.send_deletion_cancelled(user.email)
    return user


@router.get("/me/export", response_model=None, dependencies=[_read_rate_limit])
async def export_me(user: CurrentUser, db: DbSession) -> JSONResponse:
    """Download everything the platform holds about the user (GDPR Art.20).

    Reachable while locked: a user must be able to take their data with them
    before the purge. BYOK secrets are never included.
    """
    data = await user_service.export_user_data(db, user)
    filename = f"maestro-export-{datetime.now(UTC).date().isoformat()}.json"
    return JSONResponse(
        content=jsonable_encoder(data),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
