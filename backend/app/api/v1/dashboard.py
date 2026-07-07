"""Dashboard metric endpoints (real usage/cost aggregation from task sessions)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.services import billing_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def metrics(user: CurrentUser) -> dict:
    """High-level dashboard metrics (task counts, success rate, tokens)."""
    return await billing_service.metrics_summary(user.id)


@router.get("/token-usage")
async def token_usage(user: CurrentUser) -> dict:
    """Token usage summary, broken down by provider."""
    return await billing_service.usage_summary(user.id)


@router.get("/cost-summary")
async def cost_summary(user: CurrentUser) -> dict:
    """Estimated cost summary, broken down by provider."""
    return await billing_service.cost_summary(user.id)
