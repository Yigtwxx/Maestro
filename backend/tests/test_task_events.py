"""Event envelope: monotonic seq and the WebSocket snapshot cursor.

The stream now carries a per-task ``seq`` so a reconnecting client can resume
with ``?after_seq=N`` from the ``agent_logs`` source of truth instead of
replaying the whole (capped) session mirror (Backend v2 §4.2).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

from app.services import task_service


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, *args: Any, **kwargs: Any) -> _FakeCursor:
        self._docs.sort(key=lambda d: d["seq"])
        return self

    def limit(self, n: int) -> _FakeCursor:
        self._docs = self._docs[:n]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _FakeLogs:
    """Minimal ``agent_logs`` stand-in supporting find(seq>N) + projection."""

    _HIDDEN = {"task_id", "user_id", "created_at", "_id"}

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def find(self, criteria: dict[str, Any], projection: dict[str, int]):  # noqa: ANN201
        after = criteria["seq"]["$gt"]
        matched = [
            {k: v for k, v in doc.items() if k not in self._HIDDEN}
            for doc in self.docs
            if doc["seq"] > after
        ]
        return _FakeCursor(matched)


async def test_next_seq_is_monotonic() -> None:
    task_service._seq_counters.pop("seq-task", None)
    seqs = [await task_service._next_seq("seq-task") for _ in range(3)]
    assert seqs == [1, 2, 3], seqs
    task_service._seq_counters.pop("seq-task", None)


async def test_events_since_returns_events_after_the_cursor(monkeypatch) -> None:
    docs = [
        {"task_id": "t", "user_id": "u", "seq": i, "type": "node_update", "v": 1}
        for i in range(1, 6)
    ]
    monkeypatch.setattr(
        task_service, "get_task", AsyncMock(return_value={"task_id": "t"})
    )
    monkeypatch.setattr(task_service, "_logs_collection", lambda: _FakeLogs(docs))

    events, last_seq = await task_service.events_since("t", uuid.uuid4(), 2, limit=100)

    assert [e["seq"] for e in events] == [3, 4, 5], events
    assert last_seq == 5, last_seq
    assert all("user_id" not in e and "task_id" not in e for e in events), events


async def test_events_since_denies_a_non_owner(monkeypatch) -> None:
    monkeypatch.setattr(task_service, "get_task", AsyncMock(return_value=None))

    events, last_seq = await task_service.events_since("t", uuid.uuid4(), 0, limit=10)

    assert events == [], events
    assert last_seq == 0, "a rejected snapshot must not advance the cursor"
