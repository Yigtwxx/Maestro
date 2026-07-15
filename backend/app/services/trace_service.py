"""Read side of the execution-trace store (Backend v2 §4.5).

Serves the trace-waterfall and cost views from the Mongo ``trace_spans``
collection. All reads are owner-scoped: a task's trace is only returned to the
user who owns the task session, and cost aggregation filters on ``user_id``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.constants import TRACE_SPANS_MAX, MongoCollection
from app.core.database import get_mongo_db
from app.services import task_service

_INPUT_ATTR = "gen_ai.usage.input_tokens"
_OUTPUT_ATTR = "gen_ai.usage.output_tokens"


def _spans_collection():  # noqa: ANN202 - Motor collection
    return get_mongo_db()[MongoCollection.TRACE_SPANS.value]


async def get_trace(task_id: str, user_id: uuid.UUID) -> list[dict[str, Any]] | None:
    """Owner-scoped span list for one task, in start order (the waterfall).

    Returns ``None`` when the task is not found or not owned (the endpoint maps
    that to 404). An owned task with no spans (tracing was off) returns ``[]``.
    """
    if await task_service.get_task(task_id, user_id) is None:
        return None
    cursor = (
        _spans_collection()
        .find({"trace_id": task_id, "user_id": str(user_id)}, {"_id": 0})
        .sort("start_time", 1)
        .limit(TRACE_SPANS_MAX)
    )
    return [span async for span in cursor]


async def get_trace_summary(task_id: str, user_id: uuid.UUID) -> dict[str, Any] | None:
    """Per-node token/cost rollup for one task, plus totals.

    Groups spans by ``name`` (e.g. ``agent:coder``, ``llm.chat``, ``review``),
    summing tokens (from the llm spans' gen_ai usage attributes) and cost.
    """
    spans = await get_trace(task_id, user_id)
    if spans is None:
        return None

    nodes: dict[str, dict[str, Any]] = {}
    total_cost = 0.0
    total_input = 0
    total_output = 0
    for span in spans:
        attrs = span.get("attributes") or {}
        node = nodes.setdefault(
            span["name"],
            {
                "name": span["name"],
                "kind": span["kind"],
                "count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_ms": 0,
            },
        )
        node["count"] += 1
        node["input_tokens"] += int(attrs.get(_INPUT_ATTR, 0) or 0)
        node["output_tokens"] += int(attrs.get(_OUTPUT_ATTR, 0) or 0)
        node["cost_usd"] += float(span.get("cost_usd", 0.0) or 0.0)
        node["duration_ms"] += int(span.get("duration_ms", 0) or 0)
        total_cost += float(span.get("cost_usd", 0.0) or 0.0)
        total_input += int(attrs.get(_INPUT_ATTR, 0) or 0)
        total_output += int(attrs.get(_OUTPUT_ATTR, 0) or 0)

    return {
        "task_id": task_id,
        "span_count": len(spans),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": round(total_cost, 6),
        "nodes": [
            {**node, "cost_usd": round(node["cost_usd"], 6)} for node in nodes.values()
        ],
    }


async def get_costs(user_id: uuid.UUID, *, days: int, group_by: str) -> dict[str, Any]:
    """Cost/token totals for a user over a window, bucketed by ``group_by``.

    ``day`` and ``model`` aggregate directly in Mongo. ``domain`` needs the
    per-trace domain (carried on the ``step:execute`` span, not the llm spans
    that hold cost), so cost is first rolled up per trace, then attributed to
    each trace's domain.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    coll = _spans_collection()
    match = {"user_id": str(user_id), "start_time": {"$gte": since}}

    if group_by == "domain":
        buckets = await _costs_by_domain(coll, match)
    else:
        key = (
            {"$dateToString": {"format": "%Y-%m-%d", "date": "$start_time"}}
            if group_by == "day"
            else "$attributes.gen_ai.response.model"
        )
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": key,
                    "cost_usd": {"$sum": "$cost_usd"},
                    "input_tokens": {"$sum": f"${'attributes.' + _INPUT_ATTR}"},
                    "output_tokens": {"$sum": f"${'attributes.' + _OUTPUT_ATTR}"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        buckets = [
            {
                "key": row["_id"] if row["_id"] is not None else "unknown",
                "cost_usd": round(row.get("cost_usd", 0.0) or 0.0, 6),
                "input_tokens": int(row.get("input_tokens", 0) or 0),
                "output_tokens": int(row.get("output_tokens", 0) or 0),
            }
            async for row in coll.aggregate(pipeline)
        ]

    total = round(sum(b["cost_usd"] for b in buckets), 6)
    return {
        "days": days,
        "group_by": group_by,
        "total_cost_usd": total,
        "buckets": buckets,
    }


async def _costs_by_domain(
    coll,  # noqa: ANN001 - Motor collection
    match: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attribute per-trace cost to the domain on that trace's execute span."""
    # 1) cost + tokens per trace (from the cost-bearing llm spans).
    per_trace = {
        row["_id"]: row
        async for row in coll.aggregate(
            [
                {"$match": match},
                {
                    "$group": {
                        "_id": "$trace_id",
                        "cost_usd": {"$sum": "$cost_usd"},
                        "input_tokens": {"$sum": f"${'attributes.' + _INPUT_ATTR}"},
                        "output_tokens": {"$sum": f"${'attributes.' + _OUTPUT_ATTR}"},
                    }
                },
            ]
        )
    }
    # 2) domain per trace (the execute step span carries maestro.domain).
    domains: dict[str, str] = {}
    async for span in coll.find(
        {**match, "name": "step:execute"},
        {"_id": 0, "trace_id": 1, "attributes.maestro.domain": 1},
    ):
        domain = (span.get("attributes") or {}).get("maestro.domain")
        if domain:
            domains[span["trace_id"]] = domain

    buckets: dict[str, dict[str, Any]] = {}
    for trace_id, agg in per_trace.items():
        domain = domains.get(trace_id, "unknown")
        bucket = buckets.setdefault(
            domain,
            {"key": domain, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0},
        )
        bucket["cost_usd"] += float(agg.get("cost_usd", 0.0) or 0.0)
        bucket["input_tokens"] += int(agg.get("input_tokens", 0) or 0)
        bucket["output_tokens"] += int(agg.get("output_tokens", 0) or 0)
    return [
        {**b, "cost_usd": round(b["cost_usd"], 6)}
        for b in sorted(buckets.values(), key=lambda b: b["key"])
    ]
