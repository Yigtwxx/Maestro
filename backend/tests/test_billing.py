"""Unit tests for dashboard usage/cost aggregation (pure functions, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import billing_service

_DOCS = [
    {"status": "completed", "provider": "ollama", "metadata": {"total_tokens": 10}},
    {"status": "completed", "provider": "openai", "metadata": {"total_tokens": 20}},
    {"status": "failed", "provider": "ollama", "metadata": {"total_tokens": 5}},
    {"status": "running", "provider": "ollama", "metadata": {}},
]

_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _trend_doc(status: str, tokens: int, created_at: datetime) -> dict:
    return {
        "status": status,
        "provider": "ollama",
        "metadata": {"total_tokens": tokens},
        "created_at": created_at,
    }


def test_aggregate_usage_counts_tokens_and_success_rate():
    usage = billing_service.aggregate_usage(_DOCS)
    assert usage["total_tokens"] == 35, usage
    assert usage["total_tasks"] == 4, usage
    # completed=2 of terminal=3 (2 completed + 1 failed) -> 0.6667
    assert usage["success_rate"] == 0.6667, usage
    assert usage["by_provider"]["ollama"]["tasks"] == 3, usage


def test_aggregate_metrics_splits_states():
    metrics = billing_service.aggregate_metrics(_DOCS)
    assert metrics["running_tasks"] == 1, metrics
    assert metrics["completed_tasks"] == 2, metrics
    assert metrics["failed_tasks"] == 1, metrics
    assert metrics["avg_tokens_per_task"] == 9, metrics  # round(35/4)


def test_aggregate_cost_only_bills_paid_providers():
    cost = billing_service.aggregate_cost(_DOCS)
    assert cost["by_provider"]["ollama"] == 0.0, cost
    # openai: 20/1000 * 0.0015 = 0.00003
    assert cost["by_provider"]["openai"] == 0.00003, cost
    assert cost["total_cost"] == 0.00003, cost


def test_aggregate_usage_empty_is_safe():
    usage = billing_service.aggregate_usage([])
    assert usage["success_rate"] == 0.0, usage
    assert usage["total_tokens"] == 0, usage


def test_aggregate_trends_buckets_by_utc_day():
    docs = [
        _trend_doc("completed", 100, datetime(2026, 7, 11, 8, 0, tzinfo=UTC)),
        _trend_doc("completed", 50, datetime(2026, 7, 11, 9, 0, tzinfo=UTC)),
        _trend_doc("failed", 30, datetime(2026, 7, 10, 8, 0, tzinfo=UTC)),
        _trend_doc("completed", 10, datetime(2026, 6, 1, 8, 0, tzinfo=UTC)),  # old
    ]

    trends = billing_service.aggregate_trends(docs, now=_NOW, days=14)

    assert trends["window_days"] == 14, trends
    assert len(trends["days"]) == 14, trends
    assert trends["days"][-1] == "2026-07-11", trends
    assert trends["tasks"][-1] == 2, trends
    assert trends["tasks"][-2] == 1, trends
    assert sum(trends["tasks"]) == 3, trends  # the June doc is outside the window
    assert trends["tokens"][-1] == 150, trends
    assert trends["completed"][-1] == 2, trends
    assert trends["failed"][-2] == 1, trends
    assert trends["success_rate"][-1] == 1.0, trends
    assert trends["success_rate"][-2] == 0.0, trends
    assert trends["avg_tokens_per_task"][-1] == 75, trends


def test_aggregate_trends_day_without_terminal_tasks_has_null_rate():
    # A running-only day counts toward `tasks` but has no success verdict yet.
    docs = [_trend_doc("running", 0, datetime(2026, 7, 11, 8, 0, tzinfo=UTC))]

    trends = billing_service.aggregate_trends(docs, now=_NOW, days=3)

    assert trends["tasks"] == [0, 0, 1], trends
    assert trends["success_rate"] == [None, None, None], trends
    assert trends["avg_tokens_per_task"] == [None, None, 0], trends


def test_aggregate_trends_skips_docs_without_created_at():
    docs = [{"status": "completed", "metadata": {"total_tokens": 10}}]

    trends = billing_service.aggregate_trends(docs, now=_NOW, days=3)

    assert trends["tasks"] == [0, 0, 0], trends


def test_aggregate_trends_failed_includes_timeout():
    docs = [
        _trend_doc("timeout", 5, datetime(2026, 7, 11, 8, 0, tzinfo=UTC)),
        _trend_doc("failed", 5, datetime(2026, 7, 11, 9, 0, tzinfo=UTC)),
        _trend_doc("cancelled", 5, datetime(2026, 7, 11, 10, 0, tzinfo=UTC)),
    ]

    trends = billing_service.aggregate_trends(docs, now=_NOW, days=1)

    assert trends["failed"] == [2], trends  # cancelled is terminal but not failed
    assert trends["success_rate"] == [0.0], trends
