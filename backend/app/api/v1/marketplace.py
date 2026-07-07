"""Marketplace endpoints: browse, publish (with security scan), install."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser
from app.schemas.agent import AgentConfigPublic
from app.schemas.marketplace import MarketplaceItemPublic, MarketplacePublish
from app.services import marketplace_service
from app.services.marketplace_service import MarketplaceSecurityError

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("", response_model=list[MarketplaceItemPublic])
async def list_marketplace(user: CurrentUser) -> list[dict]:
    """List published agent teams."""
    return await marketplace_service.list_items()


@router.post(
    "",
    response_model=MarketplaceItemPublic,
    status_code=status.HTTP_201_CREATED,
)
async def publish_item(payload: MarketplacePublish, user: CurrentUser) -> dict:
    """Publish an agent team (runs a mandatory security scan, CLAUDE.md §9.3)."""
    try:
        return await marketplace_service.publish(user.id, payload)
    except MarketplaceSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/{item_id}", response_model=MarketplaceItemPublic)
async def get_item(item_id: str, user: CurrentUser) -> dict:
    """Return a single published item."""
    item = await marketplace_service.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    return item


@router.post(
    "/{item_id}/install",
    response_model=AgentConfigPublic,
    status_code=status.HTTP_201_CREATED,
)
async def install_item(item_id: str, user: CurrentUser) -> dict:
    """Install an item into the caller's custom agents (one-click, CLAUDE.md §8)."""
    agent = await marketplace_service.install(user.id, item_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    return agent


@router.get("/{item_id}/reviews")
async def item_reviews(item_id: str, user: CurrentUser) -> list[dict]:
    """Return reviews for an item (ratings arrive in a later round)."""
    return await marketplace_service.reviews(item_id)
