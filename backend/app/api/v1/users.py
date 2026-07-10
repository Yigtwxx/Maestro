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
from app.core.deps import ActiveUser, CurrentUser, DbSession
from app.core.security import hash_password, verify_password
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.user import (
    AccountDelete,
    AccountDeletionStatus,
    PasswordChange,
    UserUpdate,
)
from app.services import billing_service, user_service
from app.utils.rate_limiter import rate_limit

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
    payload: PasswordChange, user: ActiveUser, db: DbSession
) -> None:
    """Change the current user's password (requires the current one)."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()


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
    # Stop billing a user who can no longer use the product. Only a paid
    # subscription is cancelled: a trial charges nothing, so cancelling it would
    # merely strip the remaining trial days from anyone who restores. Restoring
    # does not resurrect a cancelled paid plan -- the user resubscribes.
    subscription = await billing_service.get_subscription(db, user.id)
    if (
        subscription is not None
        and SubscriptionStatus(subscription.status) is SubscriptionStatus.ACTIVE
    ):
        await billing_service.cancel(db, user)
    await db.commit()
    await db.refresh(user)
    return _deletion_status(user.deletion_requested_at)


@router.post(
    "/me/deletion/cancel", response_model=UserPublic, dependencies=[_write_rate_limit]
)
async def cancel_deletion(user: CurrentUser, db: DbSession) -> User:
    """Restore an account scheduled for deletion. Idempotent when not locked."""
    user.deletion_requested_at = None
    await db.commit()
    await db.refresh(user)
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
