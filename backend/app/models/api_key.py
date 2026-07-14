"""BYOK API-key ORM model (PostgreSQL).

The provider secret is stored **encrypted** (AES-256-GCM) in ``encrypted_key``.
Plaintext is never persisted or returned to clients.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.user import User


class ApiKey(Base, TimestampMixin):
    """An encrypted, user-owned provider API key (BYOK)."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    encrypted_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(120))
    # Masked hint for display only (e.g. "****abcd") — not the real key.
    key_hint: Mapped[str] = mapped_column(String(16), default="****")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only set for the "custom" provider: the user's OpenAI-compatible endpoint
    # and the model to request there. NULL for all named providers.
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys", foreign_keys=[user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ApiKey id={self.id} provider={self.provider!r}>"
