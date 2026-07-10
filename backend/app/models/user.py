"""User ORM model (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SubscriptionPlan
from app.models.base import Base, TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.api_key import ApiKey


class User(Base, TimestampMixin):
    """A registered platform user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Denormalized cache of the active subscription's plan, kept in sync by
    # billing_service within the same transaction as the subscription row.
    subscription_tier: Mapped[str] = mapped_column(
        String(20), default=SubscriptionPlan.STARTER.value
    )
    # The first-month discount is once per user, ever. Kept here rather than on
    # the subscription so cancelling and resubscribing cannot reclaim it.
    #
    # Accepted trade-off: this row is destroyed when the account is purged, so a
    # purged user re-registering the same email reclaims the discount. Keeping an
    # email-keyed suppression list would mean processing personal data after an
    # erasure request -- not justifiable to protect a one-time 50% discount.
    first_discount_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Default LLM "brain" for tasks; NULL means the free local tier (ollama).
    default_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # NULL means active. Once set, the account is locked out of every product
    # endpoint and is purged ACCOUNT_DELETION_GRACE_DAYS later. The purge date is
    # derived, never stored, so the grace window can't drift per row.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ApiKey.user_id",
    )

    __table_args__ = ({"comment": "Platform users"},)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r}>"
