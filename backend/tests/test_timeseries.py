"""Unit tests for the UTC daily-bucketing helpers (pure functions, no DB)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.utils.timeseries import bucket_daily_counts, day_index, utc_day_window

_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def test_utc_day_window_is_oldest_first_and_ends_today():
    window = utc_day_window(_NOW, 14)
    assert len(window) == 14, window
    assert window[0] == date(2026, 6, 28), window
    assert window[-1] == date(2026, 7, 11), window
    assert window == sorted(window), window


def test_utc_day_window_converts_now_to_utc_before_taking_the_date():
    # 01:00+03:00 on Jul 12 is still Jul 11 in UTC.
    local_now = datetime(2026, 7, 12, 1, 0, tzinfo=timezone(timedelta(hours=3)))
    window = utc_day_window(local_now, 7)
    assert window[-1] == date(2026, 7, 11), window


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        (datetime(2026, 6, 28, 0, 0, tzinfo=UTC), 0),  # oldest-day midnight edge
        (datetime(2026, 7, 11, 23, 59, tzinfo=UTC), 13),
        (datetime(2026, 6, 27, 23, 59, tzinfo=UTC), None),  # just before window
        (datetime(2026, 7, 12, 0, 0, tzinfo=UTC), None),  # tomorrow
    ],
)
def test_day_index_boundaries(ts: datetime, expected: int | None):
    window = utc_day_window(_NOW, 14)
    assert day_index(ts, window) == expected, ts


def test_day_index_treats_naive_datetimes_as_utc():
    window = utc_day_window(_NOW, 14)
    assert day_index(datetime(2026, 7, 11, 8, 0), window) == 13


def test_bucket_daily_counts_fills_hits_and_leaves_zeros():
    window = utc_day_window(_NOW, 3)  # Jul 9, 10, 11
    counts = bucket_daily_counts(
        [
            datetime(2026, 7, 9, 10, 0, tzinfo=UTC),
            datetime(2026, 7, 11, 1, 0, tzinfo=UTC),
            datetime(2026, 7, 11, 2, 0, tzinfo=UTC),
            datetime(2026, 7, 1, 0, 0, tzinfo=UTC),  # outside: dropped
        ],
        window,
    )
    assert counts == [1, 0, 2], counts


def test_bucket_daily_counts_empty_input_is_all_zeros():
    window = utc_day_window(_NOW, 5)
    assert bucket_daily_counts([], window) == [0, 0, 0, 0, 0]
