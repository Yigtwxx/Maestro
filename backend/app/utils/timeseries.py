"""UTC daily-bucketing helpers for trend sparklines.

Pure functions with no I/O so the aggregators built on top stay unit-testable
without a live database (same contract as ``billing_service.aggregate_*``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta


def as_utc(ts: datetime) -> datetime:
    """Treat naive datetimes as UTC (test fakes may hand them back without tz)."""
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def utc_day_window(now: datetime, days: int) -> list[date]:
    """The last ``days`` UTC calendar days, oldest first, ending today."""
    today = as_utc(now).astimezone(UTC).date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def day_index(ts: datetime, window: list[date]) -> int | None:
    """Position of ``ts`` in the window, or None when it falls outside."""
    day = as_utc(ts).astimezone(UTC).date()
    if not window or day < window[0] or day > window[-1]:
        return None
    return (day - window[0]).days


def bucket_daily_counts(
    timestamps: Iterable[datetime], window: list[date]
) -> list[int]:
    """Count timestamps per window day; days without hits stay zero."""
    counts = [0] * len(window)
    for ts in timestamps:
        index = day_index(ts, window)
        if index is not None:
            counts[index] += 1
    return counts
