"""Tests for the marketplace install-trend series.

The bucketing is a pure function; the service-level tests fake both Mongo
collections (items and install events) in memory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services import marketplace_service

_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _event(item_id: str, created_at: datetime) -> dict[str, Any]:
    return {"item_id": item_id, "created_at": created_at}


# --- bucket_install_history (pure) -----------------------------------------


def test_bucket_install_history_counts_per_day_and_zero_fills():
    events = [
        _event("a", datetime(2026, 7, 11, 1, 0, tzinfo=UTC)),
        _event("a", datetime(2026, 7, 11, 2, 0, tzinfo=UTC)),
        _event("a", datetime(2026, 7, 9, 1, 0, tzinfo=UTC)),
    ]

    history = marketplace_service.bucket_install_history(
        events, ["a"], now=_NOW, days=3
    )

    assert history["a"] == [1, 0, 2], history


def test_bucket_install_history_item_without_events_is_none():
    events = [_event("a", datetime(2026, 7, 11, 1, 0, tzinfo=UTC))]

    history = marketplace_service.bucket_install_history(
        events, ["a", "b"], now=_NOW, days=3
    )

    assert history["a"] == [0, 0, 1], history
    assert history["b"] is None, history


def test_bucket_install_history_drops_out_of_window_and_unknown_events():
    events = [
        _event("a", datetime(2026, 6, 1, 0, 0, tzinfo=UTC)),  # outside window
        _event("ghost", datetime(2026, 7, 11, 1, 0, tzinfo=UTC)),  # unknown item
    ]

    history = marketplace_service.bucket_install_history(
        events, ["a"], now=_NOW, days=3
    )

    assert history["a"] is None, history


# --- service-level (fake Mongo) ---------------------------------------------


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, *_args: Any) -> _FakeCursor:
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _FakeCollection:
    """Just enough of a Motor collection for the trend code paths."""

    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = docs or []
        self.update_one = AsyncMock()

    def find(self, _filter: dict, projection: dict | None = None) -> _FakeCursor:
        excluded = {k for k, v in (projection or {}).items() if v == 0}
        return _FakeCursor(
            [{k: v for k, v in doc.items() if k not in excluded} for doc in self.docs]
        )

    async def find_one(self, query: dict, projection: dict | None = None) -> Any:
        excluded = {k for k, v in (projection or {}).items() if v == 0}
        for doc in self.docs:
            if doc["id"] == query["id"]:
                return {k: v for k, v in doc.items() if k not in excluded}
        return None

    async def insert_one(self, document: dict) -> None:
        self.docs.append(document)


def _item(item_id: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": f"Team {item_id}",
        "description": "A team.",
        "domain": "finance",
        "system_prompt": "You are a finance analyst.",
        "tools": [],
        "installs": 0,
        "created_at": _NOW,
    }


@pytest.fixture
def fake_collections(monkeypatch) -> tuple[_FakeCollection, _FakeCollection]:
    items = _FakeCollection()
    installs = _FakeCollection()
    monkeypatch.setattr(marketplace_service, "_collection", lambda: items)
    monkeypatch.setattr(marketplace_service, "_installs_collection", lambda: installs)
    return items, installs


async def test_install_records_an_anonymous_timestamped_event(
    fake_collections, monkeypatch
):
    items, installs = fake_collections
    items.docs.append(_item("a"))
    monkeypatch.setattr(
        marketplace_service.agent_service,
        "create_agent",
        AsyncMock(return_value={"id": "agent-1"}),
    )

    agent = await marketplace_service.install(_USER_ID, "a")

    assert agent == {"id": "agent-1"}, agent
    assert len(installs.docs) == 1, installs.docs
    event = installs.docs[0]
    assert event["item_id"] == "a", event
    assert isinstance(event["created_at"], datetime), event
    assert "user_id" not in event, "install events must stay anonymous"
    items.update_one.assert_awaited_once_with({"id": "a"}, {"$inc": {"installs": 1}})


async def test_list_items_attaches_install_history(fake_collections):
    items, installs = fake_collections
    items.docs.extend([_item("a"), _item("b")])
    installs.docs.append(_event("a", datetime.now(UTC) - timedelta(hours=1)))

    listed = await marketplace_service.list_items()

    by_id = {item["id"]: item for item in listed}
    history = by_id["a"]["install_history"]
    assert history is not None and sum(history) == 1, history
    assert by_id["b"]["install_history"] is None, by_id["b"]
