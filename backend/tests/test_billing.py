"""Unit tests for dashboard usage/cost aggregation (pure functions, no DB)."""

from __future__ import annotations

from app.services import billing_service

_DOCS = [
    {"status": "completed", "provider": "ollama", "metadata": {"total_tokens": 10}},
    {"status": "completed", "provider": "openai", "metadata": {"total_tokens": 20}},
    {"status": "failed", "provider": "ollama", "metadata": {"total_tokens": 5}},
    {"status": "running", "provider": "ollama", "metadata": {}},
]


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
