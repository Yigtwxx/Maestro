"""User ORM model (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import UserRole
from app.models.base import Base, TimestampMixin, _uuid_pk

# JSONB on PostgreSQL, portable JSON elsewhere (SQLite in tests).
_JSON = JSON().with_variant(JSONB(), "postgresql")

if TYPE_CHECKING:
    from app.models.api_key import ApiKey


class User(Base, TimestampMixin):
    """A registered platform user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # The canonical form of `email`: `you+1@gmail.com`, `you+2@gmail.com` and
    # `y.o.u@gmail.com` all reduce to `you@gmail.com`, so the unique index here
    # bounds accounts per *mailbox* rather than per typed string. Computed by
    # `utils.email_hygiene.canonical_for_storage` at every write.
    #
    # Nullable, and the NULLs are load-bearing rather than incidental --
    # Postgres unique indexes do not conflict on NULL, which is what carries
    # both exceptions: an operator's admin address (exempt, so unbounded) and
    # accounts that already collided when 0019 ran (grandfathered).
    canonical_email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True, default=None
    )
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Profile personalization. The avatar is a client-rendered monogram, not an
    # uploaded image: only a palette key + optional emoji are stored (no blob).
    bio: Mapped[str | None] = mapped_column(String(280), nullable=True)
    avatar_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Denormalized cache of the active subscription's plan, kept in sync by
    # billing_service within the same transaction as the subscription row.
    # NULL = no subscription (fresh accounts). Known limit: with no scheduler,
    # a canceled subscription past its period end keeps its stale tier here.
    subscription_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Default LLM "brain" for tasks; NULL means the local model (ollama).
    default_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Per-role model preferences applied when a task leaves the model unset,
    # e.g. {"main": "claude-opus-4-8", "subagent": "claude-haiku-4-5"}. JSON so
    # the roster of roles can grow without a migration (Backend v2 §4.4).
    model_preferences: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    # TOTP two-factor auth. The secret is AES-256-GCM encrypted at rest (reusing
    # the BYOK master key); it is never returned once enrolled. NULL means never
    # set up. ``totp_enabled`` gates the second login step.
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Whether the account's email address has been confirmed via the emailed
    # link. Gates task start and API-key creation while false (soft gate,
    # disabled entirely by EMAIL_VERIFICATION_REQUIRED=false).
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Account preferences. ``timezone`` is an IANA name (NULL = client-local);
    # ``default_reviewer_enabled`` seeds a task's reviewer toggle when the
    # request leaves it unset, and ``default_tracing_enabled`` does the same for
    # execution tracing (falling through to TRACING_ENABLED when both are off).
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_reviewer_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    default_tracing_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # NULL means active. Once set, the account is locked out of every product
    # endpoint and is purged ACCOUNT_DELETION_GRACE_DAYS later. The purge date is
    # derived, never stored, so the grace window can't drift per row.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Authorization role. ``admin`` unlocks the moderation surface, an unmetered
    # task quota, and the email-verification bypass. Checked fresh off this row
    # on every request (never trusted from a JWT claim) so a demotion takes
    # effect immediately instead of lingering for the token's lifetime.
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.USER.value, server_default=UserRole.USER.value
    )
    # NULL means active. A moderator sets this to lock an abusive account out of
    # every product endpoint (same enforcement point as deletion). Unlike
    # deletion it is NOT user-cancelable: only a moderator can lift a suspension.
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ApiKey.user_id",
    )

    @property
    def two_factor_enabled(self) -> bool:
        """Public-facing alias for ``totp_enabled`` (used by UserPublic)."""
        return self.totp_enabled

    __table_args__ = ({"comment": "Platform users"},)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r}>"
