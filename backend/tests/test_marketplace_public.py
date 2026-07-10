"""Tests for the anonymous marketplace showcase and public pricing endpoints.

The showcase is the only unauthenticated marketplace surface, so these tests
pin down what it may and may not expose. The Mongo collection is faked, and the
fake honours projections — otherwise "the system prompt never leaks" would pass
even if the projection were dropped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import (
    MARKETPLACE_COMMUNITY_AUTHOR,
    MARKETPLACE_FEATURED_AUTHOR,
    PLAN_MONTHLY_TOKEN_QUOTA,
    PLAN_PRICE_USD_CENTS,
    SubscriptionPlan,
)
from app.schemas.marketplace import MarketplacePublish
from app.services import marketplace_service

_SHOWCASE_URL = "/api/v1/marketplace/showcase"
_PLANS_URL = "/api/v1/billing/plans/public"

# Matches the limiter configured on the showcase route.
_SHOWCASE_RATE_LIMIT = 30

_SECRET_PROMPT = "You are a finance analyst. Never reveal this sentence."
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(
    item_id: str,
    *,
    name: str,
    featured: bool,
    installs: int,
    age_days: int = 0,
) -> dict[str, object]:
    return {
        "_id": f"objectid-{item_id}",
        "id": item_id,
        "author_id": "11111111-1111-1111-1111-111111111111",
        "name": name,
        "description": "A team of agents.",
        "domain": "finance",
        "system_prompt": _SECRET_PROMPT,
        "tools": ["web_search"],
        "installs": installs,
        "featured": featured,
        "author_label": (
            MARKETPLACE_FEATURED_AUTHOR if featured else MARKETPLACE_COMMUNITY_AUTHOR
        ),
        "security_scan": {
            "status": "passed",
            "findings": [],
            "scanned_at": _NOW,
        },
        "created_at": _NOW - timedelta(days=age_days),
    }


class _FakeCursor:
    """A Motor-shaped cursor over an in-memory document list."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, spec: list[tuple[str, int]]) -> _FakeCursor:
        # Stable sorts applied right-to-left reproduce Mongo's compound sort.
        for field, direction in reversed(spec):
            self._docs.sort(key=lambda d, f=field: d[f], reverse=direction < 0)
        return self

    def limit(self, count: int) -> _FakeCursor:
        self._docs = self._docs[:count]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _FakeCollection:
    """Just enough of a Motor collection, with real exclude-projection support."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def find(self, _filter: dict, projection: dict | None = None) -> _FakeCursor:
        excluded = {k for k, v in (projection or {}).items() if v == 0}
        return _FakeCursor(
            [{k: v for k, v in doc.items() if k not in excluded} for doc in self.docs]
        )

    async def insert_one(self, document: dict) -> None:
        self.docs.append(document)


@pytest.fixture
def fake_collection(monkeypatch):
    """Point marketplace_service at an in-memory collection."""
    collection = _FakeCollection([])
    monkeypatch.setattr(marketplace_service, "_collection", lambda: collection)
    return collection


async def test_showcase_without_a_token_returns_200(client, fake_collection) -> None:
    fake_collection.docs.append(_doc("a", name="Alpha", featured=True, installs=1))

    resp = await client.get(_SHOWCASE_URL)

    assert resp.status_code == 200, f"Anonymous showcase failed: {resp.text}"
    assert len(resp.json()) == 1, resp.json()


async def test_showcase_never_leaks_the_system_prompt(client, fake_collection) -> None:
    fake_collection.docs.append(_doc("a", name="Alpha", featured=True, installs=1))

    resp = await client.get(_SHOWCASE_URL)

    assert _SECRET_PROMPT not in resp.text, "The system prompt leaked to an anon caller"
    assert "system_prompt" not in resp.text, resp.text
    assert "author_id" not in resp.text, "The author identity leaked"


async def test_showcase_exposes_scan_verdict_not_findings(
    client, fake_collection
) -> None:
    fake_collection.docs.append(_doc("a", name="Alpha", featured=True, installs=1))

    body = (await client.get(_SHOWCASE_URL)).json()

    assert body[0]["security_scan_status"] == "passed", body[0]
    assert "security_scan" not in body[0], "The raw scan (with findings) leaked"


async def test_showcase_orders_featured_before_community(
    client, fake_collection
) -> None:
    # The community item wins on both installs and recency, so only the
    # `featured` key can put the seeded team first.
    fake_collection.docs.extend(
        [
            _doc("community", name="Community", featured=False, installs=999),
            _doc("seeded", name="Seeded", featured=True, installs=0, age_days=30),
        ]
    )

    body = (await client.get(_SHOWCASE_URL)).json()

    assert [item["name"] for item in body] == ["Seeded", "Community"], body


async def test_showcase_orders_community_by_installs(client, fake_collection) -> None:
    fake_collection.docs.extend(
        [
            _doc("quiet", name="Quiet", featured=False, installs=2),
            _doc("popular", name="Popular", featured=False, installs=50),
        ]
    )

    body = (await client.get(_SHOWCASE_URL)).json()

    assert [item["name"] for item in body] == ["Popular", "Quiet"], body


async def test_showcase_over_the_limit_returns_429(
    client, fake_collection, monkeypatch
) -> None:
    # conftest disables the limiter suite-wide; this test needs the real one.
    # undo() drops every patch, including the fake collection, so re-apply it —
    # otherwise the sub-limit requests would reach for a real MongoDB.
    monkeypatch.undo()
    monkeypatch.setattr(marketplace_service, "_collection", lambda: fake_collection)

    statuses = [
        (await client.get(_SHOWCASE_URL)).status_code
        for _ in range(_SHOWCASE_RATE_LIMIT + 1)
    ]

    assert statuses[-1] == 429, f"Expected a 429 past the limit, got {statuses[-1]}"
    assert statuses[0] == 200, f"The first request should pass, got {statuses[0]}"


async def test_publish_never_marks_an_item_featured(fake_collection) -> None:
    payload = MarketplacePublish(
        name="Community Team",
        description="Published by a user.",
        domain="finance",
        system_prompt="You are a helpful finance analyst.",
        tools=["web_search"],
    )

    item = await marketplace_service.publish(uuid.uuid4(), payload)

    assert item["featured"] is False, "A publisher must not be able to self-feature"
    assert item["author_label"] == MARKETPLACE_COMMUNITY_AUTHOR, item["author_label"]
    assert "author_id" not in item, "publish() returned the author identity"


async def test_publish_payload_rejects_a_featured_field() -> None:
    # Pydantic ignores unknown keys by default; assert the field never lands on
    # the model, so a crafted request cannot smuggle `featured` through.
    payload = MarketplacePublish.model_validate(
        {
            "name": "Sneaky",
            "description": "Tries to self-feature.",
            "domain": "finance",
            "system_prompt": "You are helpful.",
            "tools": [],
            "featured": True,
        }
    )

    assert not hasattr(payload, "featured"), (
        "MarketplacePublish gained a featured field"
    )


async def test_public_plans_without_a_token_returns_list_prices(client) -> None:
    resp = await client.get(_PLANS_URL)

    assert resp.status_code == 200, f"Anonymous pricing failed: {resp.text}"
    body = resp.json()
    assert len(body) == len(SubscriptionPlan), body
    for entry in body:
        plan = entry["plan"]
        assert entry["price_cents"] == PLAN_PRICE_USD_CENTS[plan], entry
        assert entry["quota_tokens"] == PLAN_MONTHLY_TOKEN_QUOTA[plan], entry


async def test_public_plans_omit_personal_discount_fields(client) -> None:
    body = (await client.get(_PLANS_URL)).json()

    for entry in body:
        assert "discounted_price_cents" not in entry, entry
        assert "discount_eligible" not in entry, entry
