"""Marketplace reviews: submit (upsert), list (paginated), aggregates.

The Mongo collections are faked in memory; the fakes honour projections,
upserts and the aggregation pipeline `recompute_rating` actually runs, so the
denormalized `rating_avg`/`rating_count` behaviour is exercised for real.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import marketplace_service

_ITEM_ID = "item-1"
_AUTHOR_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_REVIEWER_ID = "22222222-2222-2222-2222-222222222222"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_EMAIL = "reviewer@user.com"
_PASSWORD = "supersecret"


async def _register_and_login(client, email: str = _EMAIL) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Reviewer"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _item_doc(item_id: str = _ITEM_ID, *, author_id: str = _AUTHOR_ID) -> dict:
    return {
        "_id": f"objectid-{item_id}",
        "id": item_id,
        "author_id": author_id,
        "name": "Alpha",
        "description": "A team of agents.",
        "domain": "finance",
        "system_prompt": "You are a finance analyst.",
        "tools": ["web_search"],
        "installs": 0,
        "featured": False,
        "author_label": "Community",
        "security_scan": {"status": "passed", "findings": [], "scanned_at": _NOW},
        "created_at": _NOW,
    }


def _review_doc(
    user_id: str, *, rating: int, comment: str | None = None, age_minutes: int = 0
) -> dict:
    stamp = _NOW - timedelta(minutes=age_minutes)
    return {
        "id": f"review-{user_id}-{age_minutes}",
        "item_id": _ITEM_ID,
        "user_id": user_id,
        "rating": rating,
        "comment": comment,
        "created_at": stamp,
        "updated_at": stamp,
    }


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    """Equality match, plus the few Mongo operators the service filters with."""
    for key, value in criteria.items():
        actual = document.get(key)
        if isinstance(value, dict):
            for operator, operand in value.items():
                if operator == "$nin":
                    if actual in operand:
                        return False
                elif operator == "$ne":
                    if actual == operand:
                        return False
                elif operator == "$in":
                    if actual not in operand:
                        return False
                elif operator == "$gte":
                    if actual is None or actual < operand:
                        return False
                else:  # pragma: no cover - unmodelled operator
                    raise NotImplementedError(operator)
        elif actual != value:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, field: str, direction: int) -> _FakeCursor:
        self._docs.sort(key=lambda d: d[field], reverse=direction < 0)
        return self

    def skip(self, count: int) -> _FakeCursor:
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int) -> _FakeCursor:
        self._docs = self._docs[:count]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _FakeCollection:
    """The slice of Motor the review paths use, projections included."""

    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = docs if docs is not None else []

    def _project(self, doc: dict, projection: dict | None) -> dict:
        if not projection:
            return dict(doc)
        included = {k for k, v in projection.items() if v == 1}
        excluded = {k for k, v in projection.items() if v == 0}
        if included:
            return {k: v for k, v in doc.items() if k in included}
        return {k: v for k, v in doc.items() if k not in excluded}

    async def find_one(self, criteria: dict, projection: dict | None = None):
        for doc in self.docs:
            if _matches(doc, criteria):
                return self._project(doc, projection)
        return None

    def find(self, criteria: dict, projection: dict | None = None) -> _FakeCursor:
        return _FakeCursor(
            [self._project(d, projection) for d in self.docs if _matches(d, criteria)]
        )

    async def count_documents(self, criteria: dict) -> int:
        return sum(1 for doc in self.docs if _matches(doc, criteria))

    async def update_one(
        self, criteria: dict, update: dict, upsert: bool = False
    ) -> None:
        for doc in self.docs:
            if _matches(doc, criteria):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(criteria)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)

    def aggregate(self, pipeline: list[dict]):
        matched = [d for d in self.docs if _matches(d, pipeline[0]["$match"])]

        async def _rows():
            if matched:
                ratings = [d["rating"] for d in matched]
                yield {
                    "_id": None,
                    "avg": sum(ratings) / len(ratings),
                    "count": len(ratings),
                }

        return _rows()


@pytest.fixture
def fake_db(monkeypatch) -> tuple[_FakeCollection, _FakeCollection]:
    """Point marketplace_service at in-memory items + reviews collections."""
    items = _FakeCollection()
    reviews = _FakeCollection()
    installs = _FakeCollection()
    monkeypatch.setattr(marketplace_service, "_collection", lambda: items)
    monkeypatch.setattr(marketplace_service, "_reviews_collection", lambda: reviews)
    monkeypatch.setattr(marketplace_service, "_installs_collection", lambda: installs)
    return items, reviews


async def test_submit_review_creates_document_and_recomputes_avg(
    client, fake_db
) -> None:
    items, reviews = fake_db
    items.docs.append(_item_doc())
    reviews.docs.append(_review_doc(_OTHER_REVIEWER_ID, rating=5))
    headers = await _register_and_login(client)

    resp = await client.post(
        f"/api/v1/marketplace/{_ITEM_ID}/reviews",
        headers=headers,
        json={"rating": 3, "comment": "Solid but slow."},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rating"] == 3, body
    assert body["is_own"] is True, body
    assert "user_id" not in body, "Reviewer identity leaked to the client"
    item = items.docs[0]
    assert item["rating_avg"] == 4.0, f"(5+3)/2 expected, got {item}"
    assert item["rating_count"] == 2, item


async def test_submit_review_twice_updates_not_duplicates(client, fake_db) -> None:
    items, reviews = fake_db
    items.docs.append(_item_doc())
    headers = await _register_and_login(client)
    url = f"/api/v1/marketplace/{_ITEM_ID}/reviews"

    first = await client.post(url, headers=headers, json={"rating": 5})
    second = await client.post(url, headers=headers, json={"rating": 2})

    assert first.status_code == 200 and second.status_code == 200
    assert len(reviews.docs) == 1, f"Upsert must replace, got {reviews.docs}"
    item = items.docs[0]
    assert item["rating_avg"] == 2.0, item
    assert item["rating_count"] == 1, item


@pytest.mark.parametrize("rating", [0, 6])
async def test_submit_review_rating_out_of_bounds_returns_422(
    client, fake_db, rating
) -> None:
    items, _ = fake_db
    items.docs.append(_item_doc())
    headers = await _register_and_login(client)

    resp = await client.post(
        f"/api/v1/marketplace/{_ITEM_ID}/reviews",
        headers=headers,
        json={"rating": rating},
    )

    assert resp.status_code == 422, f"Rating {rating} must be rejected: {resp.text}"


async def test_submit_review_own_item_returns_403(client, fake_db) -> None:
    items, reviews = fake_db
    headers = await _register_and_login(client)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    items.docs.append(_item_doc(author_id=me["id"]))

    resp = await client.post(
        f"/api/v1/marketplace/{_ITEM_ID}/reviews", headers=headers, json={"rating": 5}
    )

    assert resp.status_code == 403, resp.text
    assert reviews.docs == [], "A forbidden review must not be stored"


async def test_submit_review_unknown_item_returns_404(client, fake_db) -> None:
    headers = await _register_and_login(client)

    resp = await client.post(
        "/api/v1/marketplace/missing/reviews", headers=headers, json={"rating": 5}
    )

    assert resp.status_code == 404, resp.text


async def test_list_reviews_paginates_and_marks_own(client, fake_db) -> None:
    items, reviews = fake_db
    items.docs.append(_item_doc())
    reviews.docs.extend(
        _review_doc(f"user-{n}", rating=4, age_minutes=n) for n in range(1, 4)
    )
    headers = await _register_and_login(client)
    url = f"/api/v1/marketplace/{_ITEM_ID}/reviews"
    await client.post(url, headers=headers, json={"rating": 5, "comment": "Mine."})

    body = (await client.get(f"{url}?limit=2&offset=0", headers=headers)).json()

    assert body["total"] == 4, body
    assert len(body["items"]) == 2, body
    # The caller's review is the newest write, so it leads the first page.
    assert body["items"][0]["is_own"] is True, body
    assert body["items"][1]["is_own"] is False, body
    assert body["my_review"] is not None and body["my_review"]["rating"] == 5, body


async def test_list_reviews_unknown_item_returns_404(client, fake_db) -> None:
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/marketplace/missing/reviews", headers=headers)

    assert resp.status_code == 404, resp.text


async def test_list_items_without_rating_fields_serializes_defaults(
    client, fake_db
) -> None:
    """Items published before reviews existed must still serialize."""
    items, _ = fake_db
    items.docs.append(_item_doc())  # no rating_avg / rating_count keys
    headers = await _register_and_login(client)

    resp = await client.get("/api/v1/marketplace", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["rating_avg"] is None, body[0]
    assert body[0]["rating_count"] == 0, body[0]
