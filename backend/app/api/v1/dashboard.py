"""Dashboard metric endpoints (real usage/cost aggregation from task sessions)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.constants import RATE_LIMIT_READ
from app.core.deps import ActiveUser
from app.services import billing_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Each of these aggregates over Mongo; the dashboard polls all three together.
_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="dashboard")


@router.get("/metrics", dependencies=[_read_rate_limit])
async def metrics(user: ActiveUser) -> dict:
    """High-level dashboard metrics (task counts, success rate, tokens)."""
    return await billing_service.metrics_summary(user.id)


@router.get("/token-usage", dependencies=[_read_rate_limit])
async def token_usage(user: ActiveUser) -> dict:
    """Token usage summary, broken down by provider."""
    return await billing_service.usage_summary(user.id)


@router.get("/cost-summary", dependencies=[_read_rate_limit])
async def cost_summary(user: ActiveUser) -> dict:
    """Estimated cost summary, broken down by provider."""
    return await billing_service.cost_summary(user.id)
