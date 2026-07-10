"""Usage-record ORM model (PostgreSQL).

Append-only ledger of token consumption. This -- not MongoDB -- is what quota
enforcement trusts. One row per terminal task; ``task_id`` is unique so a retry
of the recording path cannot double-charge.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Base, TimestampMixin, _uuid_pk


class UsageRecord(Base, TimestampMixin):
    """Tokens a single task consumed, charged to a billing period."""

    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE")
    )
    task_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    tokens: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    # Denormalized from the subscription so period sums are a single-table scan.
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_usage_records_user_period", "user_id", "period_start"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<UsageRecord task_id={self.task_id!r} tokens={self.tokens}>"
