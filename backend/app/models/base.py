"""SQLAlchemy declarative base and shared column types.

`GUID` is a portable UUID type: native ``UUID`` on PostgreSQL and ``CHAR(36)``
elsewhere (e.g. SQLite used in tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CHAR, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class GUID(TypeDecorator):
    """Platform-independent UUID type (PostgreSQL native, CHAR(36) fallback)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _uuid_pk() -> Mapped[uuid.UUID]:
    """Primary-key column: UUID, generated app-side."""
    return mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Adds created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
