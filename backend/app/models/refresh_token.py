"""Refresh-token ORM model (PostgreSQL) for rotation + reuse-detection.

Each row is a single, one-time-use refresh token identified by its JWT ``jti``.
On refresh the presented row is revoked and a successor is issued in the same
``family_id`` lineage. Replaying an already-revoked token is treated as theft:
the whole family is revoked (see ``services.auth_service``). Access tokens stay
stateless, so revocation only takes effect at the next refresh (CLAUDE.md §9.4).
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


class RefreshToken(Base, TimestampMixin):
    """A server-side record of an issued refresh token (one row per ``jti``)."""

    __tablename__ = "refresh_tokens"

    # Primary key equals the JWT ``jti`` claim; the token itself is not stored.
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Session lineage: rotation keeps the family; reuse-detection revokes it whole.
    family_id: Mapped[uuid.UUID] = mapped_column(GUID(), index=True)
    # NULL means active. Set once the token is rotated, revoked, or logged out.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Mirrors the JWT ``exp``; enables opportunistic cleanup of stale rows.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Login context, captured at session start and carried forward on rotation,
    # so the user can recognise and revoke their own sessions. Nullable: older
    # rows and non-HTTP paths have none.
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Bumped to "now" on each rotation — the session's last observed activity.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        {"comment": "Server-side refresh-token records for rotation + reuse-detection"},
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        revoked = self.revoked_at is not None
        return f"<RefreshToken id={self.id} family={self.family_id} revoked={revoked}>"
