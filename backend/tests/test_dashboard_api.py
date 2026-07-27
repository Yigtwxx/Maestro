"""HTTP tests for the dashboard endpoints (metrics, token-usage, cost, costs).

The four GET routes aggregate a user's own task sessions (Mongo) and trace
spans. The load-bearing property is owner scoping: every aggregate filters on
``user_id``, so one account's numbers must never surface in another's response.
These tests wire an in-memory stand-in for the two Mongo collections and prove
both the documented body shape and that isolation, end to end over HTTP.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.models.user import User
from app.services import billing_service, trace_service

_PASSWORD = "supersecret"

_DASHBOARD_PATHS = (
    "/api/v1/dashboard/metrics",
    "/api/v1/dashboard/token-usage",
    "/api/v1/dashboard/cost-summary",
    "/api/v1/dashboard/costs",
)


# --- In-memory Mongo stand-in (mirrors the fakes in test_tracing/test_moderation) ---


def _resolve(doc: dict[str, Any], path: str) -> Any:
    """Follow a dotted Mongo field path (``$a.b.c``) into a nested document."""
    current: Any = doc
    for part in path.lstrip("$").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    """Scalar-equality and ``$gte`` matching, enough for the aggregates here."""
    for key, condition in query.items():
        actual = _resolve(doc, key)
        if isinstance(condition, dict):
            for operator, operand in condition.items():
                if operator != "$gte":
                    raise NotImplementedError(f"unsupported operator {operator}")
                if actual is None or actual < operand:
                    return False
        elif actual != condition:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, *args: Any, **kwargs: Any) -> _FakeCursor:
        return self

    def limit(self, count: int) -> _FakeCursor:
        self._docs = self._docs[:count]
        return self

    async def __aiter__(self):  # noqa: ANN204
        for doc in self._docs:
            yield doc


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def find(
        self, query: dict[str, Any] | None = None, projection: dict | None = None
    ) -> _FakeCursor:
        query = query or {}
        return _FakeCursor(
            [
                {k: v for k, v in doc.items() if k != "_id"}
                for doc in self.docs
                if _matches(doc, query)
            ]
        )

    def aggregate(self, pipeline: list[dict[str, Any]]):
        docs: list[dict[str, Any]] = list(self.docs)
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if _matches(d, stage["$match"])]
            elif "$group" in stage:
                docs = self._group(docs, stage["$group"])
            elif "$sort" in stage:
                key = next(iter(stage["$sort"]))
                docs = sorted(docs, key=lambda r: (r.get(key) is None, r.get(key)))

        async def _rows():  # noqa: ANN202
            for doc in docs:
                yield doc

        return _rows()

    @staticmethod
    def _group(
        docs: list[dict[str, Any]], spec: dict[str, Any]
    ) -> list[dict[str, Any]]:
        id_spec = spec["_id"]
        sum_fields = {name: agg["$sum"] for name, agg in spec.items() if name != "_id"}

        def key_of(doc: dict[str, Any]) -> Any:
            if isinstance(id_spec, dict):
                date_spec = id_spec["$dateToString"]
                value = _resolve(doc, date_spec["date"])
                return value.strftime(date_spec["format"])
            return _resolve(doc, id_spec)

        buckets: dict[Any, dict[str, Any]] = {}
        for doc in docs:
            key = key_of(doc)
            bucket = buckets.setdefault(
                key, {"_id": key, **{name: 0 for name in sum_fields}}
            )
            for name, path in sum_fields.items():
                bucket[name] += _resolve(doc, path) or 0
        return list(buckets.values())


class _FakeMongoDB:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = defaultdict(_FakeCollection)

    def __getitem__(self, name: str) -> _FakeCollection:
        return self.collections[name]


# --- Helpers ---------------------------------------------------------------


async def _register(client, email: str) -> dict[str, str]:  # noqa: ANN001
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD, "display_name": "Dash"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _user_id(db_session, email: str) -> str:  # noqa: ANN001
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None, f"No user seeded for {email}"
    return str(user.id)


def _session_doc(user_id: str, *, status: str, provider: str, tokens: int) -> dict:
    return {
        "user_id": user_id,
        "status": status,
        "provider": provider,
        "metadata": {"total_tokens": tokens},
        "created_at": datetime.now(UTC),
    }


def _span_doc(user_id: str, *, model: str, cost: float, inp: int, out: int) -> dict:
    return {
        "user_id": user_id,
        "trace_id": "trace-1",
        "start_time": datetime.now(UTC),
        "cost_usd": cost,
        "attributes": {
            "gen_ai": {
                "response": {"model": model},
                "usage": {"input_tokens": inp, "output_tokens": out},
            }
        },
    }


def _install_fake_mongo(monkeypatch) -> _FakeMongoDB:  # noqa: ANN001
    db = _FakeMongoDB()
    monkeypatch.setattr(billing_service, "get_mongo_db", lambda: db)
    monkeypatch.setattr(trace_service, "get_mongo_db", lambda: db)
    return db


# --- Auth ------------------------------------------------------------------


async def test_dashboard_endpoints_require_authentication(client) -> None:
    for path in _DASHBOARD_PATHS:
        resp = await client.get(path)
        assert resp.status_code in (401, 403), (
            f"{path} served an unauthenticated caller with {resp.status_code}"
        )


# --- Body shape ------------------------------------------------------------


async def test_metrics_returns_documented_counters(client, db_session, monkeypatch):
    db = _install_fake_mongo(monkeypatch)
    headers = await _register(client, "metrics@dash.com")
    user_id = await _user_id(db_session, "metrics@dash.com")
    db["task_sessions"].docs.append(
        _session_doc(user_id, status="completed", provider="openai", tokens=100)
    )

    resp = await client.get("/api/v1/dashboard/metrics", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for field in (
        "total_tasks",
        "running_tasks",
        "completed_tasks",
        "failed_tasks",
        "success_rate",
        "total_tokens",
        "avg_tokens_per_task",
        "trends",
    ):
        assert field in body, f"metrics body missing {field}: {body}"
    assert body["total_tasks"] == 1, body
    assert body["completed_tasks"] == 1, body
    assert body["total_tokens"] == 100, body


async def test_token_usage_returns_provider_breakdown(client, db_session, monkeypatch):
    db = _install_fake_mongo(monkeypatch)
    headers = await _register(client, "usage@dash.com")
    user_id = await _user_id(db_session, "usage@dash.com")
    db["task_sessions"].docs.append(
        _session_doc(user_id, status="completed", provider="openai", tokens=250)
    )

    resp = await client.get("/api/v1/dashboard/token-usage", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == user_id, body
    assert body["total_tokens"] == 250, body
    assert body["total_tasks"] == 1, body
    assert body["by_provider"]["openai"] == {"tasks": 1, "tokens": 250}, body


async def test_cost_summary_returns_usd_breakdown(client, db_session, monkeypatch):
    db = _install_fake_mongo(monkeypatch)
    headers = await _register(client, "cost@dash.com")
    user_id = await _user_id(db_session, "cost@dash.com")
    db["task_sessions"].docs.append(
        _session_doc(user_id, status="completed", provider="openai", tokens=1000)
    )

    resp = await client.get("/api/v1/dashboard/cost-summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["currency"] == "USD", body
    assert "total_cost" in body and "by_provider" in body, body
    assert body["total_cost"] >= 0.0, body


async def test_costs_returns_bucketed_window(client, db_session, monkeypatch):
    db = _install_fake_mongo(monkeypatch)
    headers = await _register(client, "costs@dash.com")
    user_id = await _user_id(db_session, "costs@dash.com")
    db["trace_spans"].docs.append(
        _span_doc(user_id, model="gpt-4o", cost=0.5, inp=100, out=50)
    )

    resp = await client.get("/api/v1/dashboard/costs", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["group_by"] == "day", body
    assert body["total_cost_usd"] == 0.5, body
    assert len(body["buckets"]) == 1, body
    assert body["buckets"][0]["cost_usd"] == 0.5, body
    assert body["buckets"][0]["input_tokens"] == 100, body


async def test_costs_rejects_unknown_group_by(client, monkeypatch) -> None:
    _install_fake_mongo(monkeypatch)
    headers = await _register(client, "badgroup@dash.com")

    resp = await client.get(
        "/api/v1/dashboard/costs", headers=headers, params={"group_by": "galaxy"}
    )
    assert resp.status_code == 400, resp.text


# --- Cross-user isolation (security-critical) ------------------------------


async def test_dashboard_metrics_do_not_leak_across_users(
    client, db_session, monkeypatch
) -> None:
    db = _install_fake_mongo(monkeypatch)
    a_headers = await _register(client, "owner@dash.com")
    b_headers = await _register(client, "stranger@dash.com")
    a_id = await _user_id(db_session, "owner@dash.com")

    # Only user A has any activity.
    db["task_sessions"].docs.extend(
        [
            _session_doc(a_id, status="completed", provider="openai", tokens=300),
            _session_doc(a_id, status="failed", provider="openai", tokens=120),
        ]
    )
    db["trace_spans"].docs.append(
        _span_doc(a_id, model="gpt-4o", cost=0.9, inp=100, out=50)
    )

    a_resp = await client.get("/api/v1/dashboard/metrics", headers=a_headers)
    a_metrics = a_resp.json()
    assert a_metrics["total_tasks"] == 2, a_metrics
    assert a_metrics["total_tokens"] == 420, a_metrics

    b_resp = await client.get("/api/v1/dashboard/metrics", headers=b_headers)
    b_metrics = b_resp.json()
    assert b_metrics["total_tasks"] == 0, (
        f"User B saw another account's tasks: {b_metrics}"
    )
    assert b_metrics["total_tokens"] == 0, b_metrics

    b_usage = (
        await client.get("/api/v1/dashboard/token-usage", headers=b_headers)
    ).json()
    assert b_usage["total_tokens"] == 0, b_usage
    assert b_usage["by_provider"] == {}, (
        f"User B inherited another account's providers: {b_usage}"
    )

    b_costs = (await client.get("/api/v1/dashboard/costs", headers=b_headers)).json()
    assert b_costs["total_cost_usd"] == 0.0, b_costs
    assert b_costs["buckets"] == [], (
        f"User B saw another account's cost buckets: {b_costs}"
    )
