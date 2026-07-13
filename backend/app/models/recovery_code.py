"""Two-factor recovery codes (PostgreSQL).

Single-use backup codes shown once when a user enables TOTP. Only an Argon2 hash
is stored; the plaintext is never persisted. A code is consumed by stamping
``used_at``. Rows cascade-delete with the owning user.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.user import User


class RecoveryCode(Base, TimestampMixin):
    """One two-factor recovery code (Argon2 hash of the plaintext)."""

    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    # NULL means unused; set once the code is redeemed at login.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RecoveryCode id={self.id} used={self.used_at is not None}>"
