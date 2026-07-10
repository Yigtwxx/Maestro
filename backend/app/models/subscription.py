"""Subscription ORM model (PostgreSQL).

One row per user. Provider fields are deliberately generic
(``provider_subscription_id``, not ``stripe_subscription_id``) so swapping the
payment processor never touches the schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PAYMENT_PROVIDER_MOCK
from app.models.base import GUID, Base, TimestampMixin, _uuid_pk


class Subscription(Base, TimestampMixin):
    """A user's current subscription and its billing period."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default=PAYMENT_PROVIDER_MOCK)
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Quota is counted against this window; usage_records rows are anchored to
    # current_period_start.
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Subscription user_id={self.user_id} plan={self.plan!r}>"
