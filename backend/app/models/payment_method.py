"""Payment-method ORM model (PostgreSQL).

Stores only what is safe to keep: card brand, last four digits and expiry. The
full card number (PAN) never reaches this table -- it lives in memory for the
duration of a single provider call and is then discarded.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PAYMENT_PROVIDER_MOCK
from app.models.base import GUID, Base, TimestampMixin, _uuid_pk


class PaymentMethod(Base, TimestampMixin):
    """A tokenized card belonging to a user."""

    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default=PAYMENT_PROVIDER_MOCK)
    provider_payment_method_id: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str] = mapped_column(String(20))
    last4: Mapped[str] = mapped_column(String(4))
    exp_month: Mapped[int] = mapped_column(Integer)
    exp_year: Mapped[int] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PaymentMethod user_id={self.user_id} brand={self.brand!r}>"
