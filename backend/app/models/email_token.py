"""Single-use email action tokens (PostgreSQL).

Backs email verification and password reset. Only a SHA-256 hash of the raw
token is stored; the plaintext exists solely inside the emailed link. A token
is consumed by stamping ``used_at``; issuing a new token for the same
(user, purpose) invalidates prior unused rows. Rows cascade-delete with the
owning user, so the account purge needs no extra step here.
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


class EmailToken(Base, TimestampMixin):
    """One single-use email action token (SHA-256 hash of the plaintext)."""

    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # EmailTokenPurpose value ("verify_email" | "reset_password").
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Indexed for the retention sweep (app.scripts.purge_email_tokens), whose
    # only predicate is expires_at < cutoff.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # NULL means unused; set when consumed or superseded by a newer token.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The typeable alternative to the link, for code-bearing purposes only
    # (NULL elsewhere). Six digits is a small keyspace, so it carries its own
    # short expiry and an attempt counter; ``used_at`` is shared with the token,
    # which is what makes redeeming either one retire both.
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    code_attempts: Mapped[int] = mapped_column(default=0, server_default="0")

    user: Mapped[User] = relationship(foreign_keys=[user_id])

    __table_args__ = ({"comment": "Single-use email action tokens (SHA-256 hashes)"},)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EmailToken id={self.id} purpose={self.purpose!r}>"
