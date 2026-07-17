"""Health probes: liveness stays dependency-free, readiness reflects services."""

from __future__ import annotations

from app.core import database


async def test_health_liveness_returns_ok(client) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}


async def test_readiness_all_dependencies_ok_returns_200(client, monkeypatch) -> None:
    async def _ok() -> None:
        return None

    async def _redis_ok() -> str:
        return "ok"

    monkeypatch.setattr(database, "ping_postgres", _ok)
    monkeypatch.setattr(database, "ping_mongo", _ok)
    monkeypatch.setattr(database, "ping_qdrant", _ok)
    monkeypatch.setattr(database, "ping_redis", _redis_ok)

    resp = await client.get("/health/ready")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready", body
    assert body["checks"] == {
        "postgres": "ok",
        "mongo": "ok",
        "qdrant": "ok",
        "redis": "ok",
    }


async def test_readiness_dependency_down_returns_503(client, monkeypatch) -> None:
    async def _ok() -> None:
        return None

    async def _boom() -> None:
        raise RuntimeError("connection refused")

    async def _redis_skipped() -> str:
        return "skipped"

    monkeypatch.setattr(database, "ping_postgres", _ok)
    monkeypatch.setattr(database, "ping_mongo", _boom)
    monkeypatch.setattr(database, "ping_qdrant", _ok)
    monkeypatch.setattr(database, "ping_redis", _redis_skipped)

    resp = await client.get("/health/ready")

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["status"] == "degraded", body
    assert body["checks"]["mongo"] == "error", body
    # A raw exception message must never leak into the probe body.
    assert "connection refused" not in resp.text


async def test_check_readiness_redis_skipped_is_not_a_failure(monkeypatch) -> None:
    async def _ok() -> None:
        return None

    async def _redis_skipped() -> str:
        return "skipped"

    monkeypatch.setattr(database, "ping_postgres", _ok)
    monkeypatch.setattr(database, "ping_mongo", _ok)
    monkeypatch.setattr(database, "ping_qdrant", _ok)
    monkeypatch.setattr(database, "ping_redis", _redis_skipped)

    ready, checks = await database.check_readiness()

    assert ready is True, checks
    assert checks["redis"] == "skipped", checks


async def test_check_readiness_times_out_slow_dependency(monkeypatch) -> None:
    import asyncio

    async def _ok() -> None:
        return None

    async def _hang() -> None:
        await asyncio.sleep(60)

    async def _redis_ok() -> str:
        return "ok"

    monkeypatch.setattr(database, "_HEALTH_PING_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(database, "ping_postgres", _ok)
    monkeypatch.setattr(database, "ping_mongo", _ok)
    monkeypatch.setattr(database, "ping_qdrant", _hang)
    monkeypatch.setattr(database, "ping_redis", _redis_ok)

    ready, checks = await database.check_readiness()

    assert ready is False, checks
    assert checks["qdrant"] == "error", checks
