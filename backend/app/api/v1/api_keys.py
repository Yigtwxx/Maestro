"""BYOK API-key management endpoints.

Keys are encrypted at rest (AES-256-GCM). Responses never include secret
material — only provider/label/hint (CLAUDE.md §9.1).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.constants import RATE_LIMIT_READ, RATE_LIMIT_WRITE
from app.core.deps import ActiveUser, DbSession
from app.core.security import encrypt_secret, mask_secret
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyCreate, ApiKeyPublic
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="api-keys")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="api-keys")


@router.get("", response_model=list[ApiKeyPublic], dependencies=[_read_rate_limit])
async def list_api_keys(user: ActiveUser, db: DbSession) -> list[ApiKey]:
    """List the current user's stored API keys (metadata only)."""
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ApiKeyPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def create_api_key(
    payload: ApiKeyCreate, user: ActiveUser, db: DbSession
) -> ApiKey:
    """Store a new encrypted API key for the current user."""
    api_key = ApiKey(
        user_id=user.id,
        provider=payload.provider.value,
        encrypted_key=encrypt_secret(payload.key),
        label=payload.label,
        key_hint=mask_secret(payload.key),
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_api_key(key_id: uuid.UUID, user: ActiveUser, db: DbSession) -> None:
    """Delete one of the current user's API keys."""
    api_key = await db.get(ApiKey, key_id)
    if api_key is None or api_key.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found."
        )
    await db.delete(api_key)
    await db.commit()
