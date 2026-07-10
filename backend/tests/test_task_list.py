"""Unit tests for task history summaries (pure function, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import task_service

_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _doc(**overrides) -> dict:
    base = {
        "task_id": "abc-123",
        "user_id": "user-1",
        "status": "completed",
        "prompt": "Summarize the market",
        "domain": "finance",
        "error": None,
        "events": [{"type": "task_started"}],
        "metadata": {"total_tokens": 42},
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    return {**base, **overrides}


def test_build_summary_keeps_core_fields():
    summary = task_service.build_summary(_doc())
    assert summary["task_id"] == "abc-123", summary
    assert summary["status"] == "completed", summary
    assert summary["domain"] == "finance", summary
    assert summary["created_at"] == _NOW, summary


def test_build_summary_drops_events_and_metadata():
    summary = task_service.build_summary(_doc())
    assert "events" not in summary, summary
    assert "metadata" not in summary, summary
    assert "user_id" not in summary, summary


def test_build_summary_truncates_long_prompt():
    prompt = "x" * 500
    summary = task_service.build_summary(_doc(prompt=prompt))
    expected_len = task_service._PROMPT_PREVIEW_LEN + 1  # + the ellipsis
    assert len(summary["prompt"]) == expected_len, summary["prompt"]
    assert summary["prompt"].endswith("…"), summary["prompt"]


def test_build_summary_keeps_short_prompt_verbatim():
    summary = task_service.build_summary(_doc(prompt="short"))
    assert summary["prompt"] == "short", summary


def test_build_summary_tolerates_missing_optional_fields():
    doc = _doc()
    del doc["domain"]
    del doc["error"]
    summary = task_service.build_summary(doc)
    assert summary["domain"] is None, summary
    assert summary["error"] is None, summary
