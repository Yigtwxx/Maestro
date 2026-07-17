"""End-to-end moderation flow over an in-memory Mongo fake.

Exercises the real service + endpoint code: publishing, hiding an item (it drops
from the public listing), hiding a review (the rating recomputes), taking down a
custom agent, and the report -> resolve -> audit lifecycle.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.core.constants import UserRole
from app.models.user import User
from app.services import marketplace_service, moderation_service

_PASSWORD = "supersecret"


# --- In-memory Mongo fake (operator-aware) ---


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    for key, value in criteria.items():
        actual = document.get(key)
        if isinstance(value, dict):
            for operator, operand in value.items():
                if operator == "$nin" and actual in operand:
                    return False
                if operator == "$ne" and actual == operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
                if operator == "$gte" and (actual is None or actual < operand):
                    return False
        elif actual != value:
            return False
    return True


def _project(doc: dict, projection: dict | None) -> dict:
    if not projection:
        return dict(doc)
    included = {k for k, v in projection.items() if v == 1}
    excluded = {k for k, v in projection.items() if v == 0}
    if included:
        return {k: v for k, v in doc.items() if k in included}
    return {k: v for k, v in doc.items() if k not in excluded}


class _Result:
    def __init__(self, matched: int) -> None:
        self.matched_count = matched
        self.modified_count = matched


class _Cursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, spec, direction: int | None = None) -> _Cursor:  # noqa: ANN001
        if isinstance(spec, str):
            self._docs.sort(key=lambda d: d.get(spec), reverse=(direction or 1) < 0)
        else:
            for field, dirn in reversed(spec):
                self._docs.sort(key=lambda d, f=field: d.get(f), reverse=dirn < 0)
        return self

    def skip(self, count: int) -> _Cursor:
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int) -> _Cursor:
        self._docs = self._docs[:count]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class _Collection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find(self, criteria: dict | None = None, projection: dict | None = None):
        criteria = criteria or {}
        return _Cursor(
            [_project(d, projection) for d in self.docs if _matches(d, criteria)]
        )

    async def find_one(self, criteria: dict, projection: dict | None = None):
        for doc in self.docs:
            if _matches(doc, criteria):
                return _project(doc, projection)
        return None

    async def count_documents(self, criteria: dict) -> int:
        return sum(1 for d in self.docs if _matches(d, criteria))

    async def insert_one(self, document: dict) -> None:
        self.docs.append(dict(document))

    async def update_one(
        self, criteria: dict, update: dict, upsert: bool = False
    ) -> _Result:
        for doc in self.docs:
            if _matches(doc, criteria):
                doc.update(update.get("$set", {}))
                return _Result(1)
        if upsert:
            doc = dict(criteria)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
        return _Result(0)

    async def update_many(self, criteria: dict, update: dict) -> _Result:
        n = 0
        for doc in self.docs:
            if _matches(doc, criteria):
                doc.update(update.get("$set", {}))
                n += 1
        return _Result(n)

    async def find_one_and_update(self, criteria: dict, update: dict):
        for doc in self.docs:
            if _matches(doc, criteria):
                before = dict(doc)
                doc.update(update.get("$set", {}))
                return before
        return None

    async def find_one_and_delete(self, criteria: dict):
        for index, doc in enumerate(self.docs):
            if _matches(doc, criteria):
                return self.docs.pop(index)
        return None

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
def mongo(monkeypatch) -> dict[str, _Collection]:
    """Wire both services at one shared set of in-memory collections."""
    collections = {
        name: _Collection()
        for name in ("items", "reviews", "installs", "reports", "actions", "agents")
    }
    monkeypatch.setattr(
        marketplace_service, "_collection", lambda: collections["items"]
    )
    monkeypatch.setattr(
        marketplace_service, "_reviews_collection", lambda: collections["reviews"]
    )
    monkeypatch.setattr(
        marketplace_service, "_installs_collection", lambda: collections["installs"]
    )
    monkeypatch.setattr(moderation_service, "_items", lambda: collections["items"])
    monkeypatch.setattr(moderation_service, "_reviews", lambda: collections["reviews"])
    monkeypatch.setattr(moderation_service, "_reports", lambda: collections["reports"])
    monkeypatch.setattr(moderation_service, "_actions", lambda: collections["actions"])
    monkeypatch.setattr(moderation_service, "_agents", lambda: collections["agents"])
    return collections


# --- Helpers ---


async def _register(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "U"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _admin(client, db, email: str) -> dict[str, str]:  # noqa: ANN001
    headers = await _register(client, email)
    user = await db.scalar(select(User).where(User.email == email))
    user.role = UserRole.ADMIN.value
    await db.commit()
    return headers


async def _publish(client, headers) -> str:  # noqa: ANN001
    resp = await client.post(
        "/api/v1/marketplace",
        headers=headers,
        json={
            "name": "Alpha",
            "description": "A helpful team.",
            "domain": "finance",
            "system_prompt": "You are a helpful finance analyst.",
            "tools": ["web_search"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Tests ---


async def test_hidden_item_drops_from_public_listing(client, db_session, mongo) -> None:
    author = await _register(client, "author@test.com")
    admin = await _admin(client, db_session, "mod@test.com")
    item_id = await _publish(client, author)

    listing = await client.get("/api/v1/marketplace", headers=author)
    assert any(i["id"] == item_id for i in listing.json()), "Item should be visible"

    hide = await client.post(
        f"/api/v1/admin/marketplace/items/{item_id}/status",
        headers=admin,
        json={"status": "hidden", "reason": "spam"},
    )
    assert hide.status_code == 200, hide.text
    assert hide.json()["status"] == "hidden"

    after = await client.get("/api/v1/marketplace", headers=author)
    assert all(i["id"] != item_id for i in after.json()), "Hidden item must disappear"
    # The admin listing still sees it, with author attribution.
    admin_list = await client.get("/api/v1/admin/marketplace/items", headers=admin)
    hidden = next(i for i in admin_list.json() if i["id"] == item_id)
    assert hidden["author_id"] is not None, "Moderator view keeps author attribution"


async def test_reinstate_makes_item_visible_again(client, db_session, mongo) -> None:
    author = await _register(client, "a2@test.com")
    admin = await _admin(client, db_session, "m2@test.com")
    item_id = await _publish(client, author)
    await client.post(
        f"/api/v1/admin/marketplace/items/{item_id}/status",
        headers=admin,
        json={"status": "hidden"},
    )

    reinstate = await client.post(
        f"/api/v1/admin/marketplace/items/{item_id}/status",
        headers=admin,
        json={"status": "published"},
    )
    assert reinstate.status_code == 200, reinstate.text
    listing = await client.get("/api/v1/marketplace", headers=author)
    assert any(i["id"] == item_id for i in listing.json()), "Reinstated item returns"


async def test_hiding_a_review_recomputes_rating(client, db_session, mongo) -> None:
    author = await _register(client, "a3@test.com")
    r1 = await _register(client, "r1@test.com")
    r2 = await _register(client, "r2@test.com")
    admin = await _admin(client, db_session, "m3@test.com")
    item_id = await _publish(client, author)

    await client.post(
        f"/api/v1/marketplace/{item_id}/reviews", headers=r1, json={"rating": 5}
    )
    await client.post(
        f"/api/v1/marketplace/{item_id}/reviews",
        headers=r2,
        json={"rating": 1, "comment": "spam spam"},
    )
    item = await client.get(f"/api/v1/marketplace/{item_id}", headers=author)
    assert item.json()["rating_avg"] == 3.0, "(5+1)/2 before moderation"

    reviews = await client.get(
        f"/api/v1/admin/marketplace/items/{item_id}/reviews", headers=admin
    )
    bad = next(r for r in reviews.json() if r["rating"] == 1)
    hide = await client.post(
        f"/api/v1/admin/marketplace/reviews/{bad['id']}/hide",
        headers=admin,
        json={"hidden": True, "reason": "abuse"},
    )
    assert hide.status_code == 200, hide.text

    item = await client.get(f"/api/v1/marketplace/{item_id}", headers=author)
    assert item.json()["rating_avg"] == 5.0, "Only the 5-star remains visible"
    assert item.json()["rating_count"] == 1, "Hidden review is excluded from the count"


async def test_report_flows_to_queue_and_resolves(client, db_session, mongo) -> None:
    author = await _register(client, "a4@test.com")
    reporter = await _register(client, "rep@test.com")
    admin = await _admin(client, db_session, "m4@test.com")
    item_id = await _publish(client, author)

    report = await client.post(
        f"/api/v1/marketplace/{item_id}/report",
        headers=reporter,
        json={"reason": "spam", "note": "clearly spam"},
    )
    assert report.status_code == 202, report.text

    queue = await client.get("/api/v1/admin/reports?status=open", headers=admin)
    assert queue.status_code == 200, queue.text
    rows = queue.json()
    assert len(rows) == 1 and rows[0]["target_id"] == item_id, rows
    report_id = rows[0]["id"]

    resolve = await client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        headers=admin,
        json={"resolution": "dismissed"},
    )
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["status"] == "dismissed"

    open_again = await client.get("/api/v1/admin/reports?status=open", headers=admin)
    assert open_again.json() == [], "The report should leave the open queue"


async def test_reporting_twice_upserts_one_row(client, db_session, mongo) -> None:
    author = await _register(client, "a5@test.com")
    reporter = await _register(client, "rep2@test.com")
    admin = await _admin(client, db_session, "m5@test.com")
    item_id = await _publish(client, author)
    url = f"/api/v1/marketplace/{item_id}/report"

    await client.post(url, headers=reporter, json={"reason": "spam"})
    await client.post(url, headers=reporter, json={"reason": "abuse"})

    queue = await client.get("/api/v1/admin/reports", headers=admin)
    assert len(queue.json()) == 1, "One reporter + one target => a single report row"
    assert queue.json()[0]["reason"] == "abuse", "Re-report refreshes the reason"


async def test_taking_down_an_item_audits_and_closes_reports(
    client, db_session, mongo
) -> None:
    author = await _register(client, "a6@test.com")
    reporter = await _register(client, "rep3@test.com")
    admin = await _admin(client, db_session, "m6@test.com")
    item_id = await _publish(client, author)
    await client.post(
        f"/api/v1/marketplace/{item_id}/report",
        headers=reporter,
        json={"reason": "malicious"},
    )

    await client.post(
        f"/api/v1/admin/marketplace/items/{item_id}/status",
        headers=admin,
        json={"status": "removed", "reason": "malicious payload"},
    )

    # The open report auto-resolves when the target is taken down.
    still_open = await client.get("/api/v1/admin/reports?status=open", headers=admin)
    assert still_open.json() == [], "Taking down the target closes its open reports"

    audit = await client.get("/api/v1/admin/audit", headers=admin)
    actions = [a["action"] for a in audit.json()]
    assert "item_removed" in actions, actions


async def test_agent_takedown_removes_and_404s_second_time(
    client, db_session, mongo
) -> None:
    admin = await _admin(client, db_session, "m7@test.com")
    mongo["agents"].docs.append(
        {"id": "agent-1", "user_id": "someone", "name": "Rogue", "routable": True}
    )

    first = await client.delete("/api/v1/admin/agents/agent-1", headers=admin)
    assert first.status_code == 200, first.text
    assert mongo["agents"].docs == [], "The agent document should be gone"

    second = await client.delete("/api/v1/admin/agents/agent-1", headers=admin)
    assert second.status_code == 404, "A second take-down finds nothing"


async def test_overview_counts_reflect_state(client, db_session, mongo) -> None:
    author = await _register(client, "a8@test.com")
    admin = await _admin(client, db_session, "m8@test.com")
    item_id = await _publish(client, author)
    await client.post(
        f"/api/v1/admin/marketplace/items/{item_id}/status",
        headers=admin,
        json={"status": "hidden"},
    )

    overview = await client.get("/api/v1/admin/overview", headers=admin)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["items_total"] == 1, body
    assert body["items_hidden"] == 1, body
    assert body["admins_total"] >= 1, body
