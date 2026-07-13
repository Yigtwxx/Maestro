"""Marketplace endpoints: browse, publish (with security scan), install.

``GET /marketplace/showcase`` is the one anonymous surface here. It serves the
public landing page and returns previews only — never a system prompt.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.constants import (
    RATE_LIMIT_PUBLIC,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
    REVIEWS_PAGE_SIZE_DEFAULT,
    REVIEWS_PAGE_SIZE_MAX,
    ReportTarget,
)
from app.core.deps import ActiveUser
from app.schemas.agent import AgentConfigPublic
from app.schemas.auth import DetailResponse
from app.schemas.marketplace import (
    MarketplaceItemPreview,
    MarketplaceItemPublic,
    MarketplacePublish,
    MarketplaceReportSubmit,
    MarketplaceReviewList,
    MarketplaceReviewPublic,
    MarketplaceReviewSubmit,
)
from app.services import marketplace_service, moderation_service
from app.services.marketplace_service import (
    MarketplaceReviewForbiddenError,
    MarketplaceSecurityError,
)
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="marketplace")
# Publishing and installing mutate state, so they are throttled harder.
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="marketplace")
# The showcase is unauthenticated, so it is throttled hardest of all.
_public_rate_limit = rate_limit(RATE_LIMIT_PUBLIC, scope="marketplace")


@router.get(
    "", response_model=list[MarketplaceItemPublic], dependencies=[_read_rate_limit]
)
async def list_marketplace(user: ActiveUser) -> list[dict]:
    """List published agent teams."""
    return await marketplace_service.list_items()


# Declared before ``/{item_id}``: FastAPI matches in registration order, and the
# path parameter would otherwise swallow the literal "showcase" segment.
@router.get(
    "/showcase",
    response_model=list[MarketplaceItemPreview],
    dependencies=[_public_rate_limit],
)
async def showcase() -> list[dict]:
    """List published agent teams for anonymous visitors (featured first)."""
    return await marketplace_service.list_showcase()


@router.post(
    "",
    response_model=MarketplaceItemPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_write_rate_limit],
)
async def publish_item(payload: MarketplacePublish, user: ActiveUser) -> dict:
    """Publish an agent team (runs a mandatory security scan, CLAUDE.md §9.3)."""
    try:
        return await marketplace_service.publish(user.id, payload)
    except MarketplaceSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/{item_id}", response_model=MarketplaceItemPublic, dependencies=[_read_rate_limit]
)
async def get_item(item_id: str, user: ActiveUser) -> dict:
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
    dependencies=[_write_rate_limit],
)
async def install_item(item_id: str, user: ActiveUser) -> dict:
    """Install an item into the caller's custom agents (one-click, CLAUDE.md §8)."""
    agent = await marketplace_service.install(user.id, item_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    return agent


@router.get(
    "/{item_id}/reviews",
    response_model=MarketplaceReviewList,
    dependencies=[_read_rate_limit],
)
async def item_reviews(
    item_id: str,
    user: ActiveUser,
    limit: int = Query(
        default=REVIEWS_PAGE_SIZE_DEFAULT, ge=1, le=REVIEWS_PAGE_SIZE_MAX
    ),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return one page of an item's reviews plus the caller's own review."""
    page = await marketplace_service.list_reviews(
        item_id, user.id, limit=limit, offset=offset
    )
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    return page


@router.post(
    "/{item_id}/reviews",
    response_model=MarketplaceReviewPublic,
    dependencies=[_write_rate_limit],
)
async def submit_review(
    item_id: str, payload: MarketplaceReviewSubmit, user: ActiveUser
) -> dict:
    """Create or replace the caller's review of an item (one per user).

    Responds 200 rather than 201: the write is an upsert, so a repeat call
    replaces the existing review instead of creating a second one.
    """
    try:
        review = await marketplace_service.submit_review(user.id, item_id, payload)
    except MarketplaceReviewForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    return review


@router.post(
    "/{item_id}/report",
    response_model=DetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_write_rate_limit],
)
async def report_item(
    item_id: str, payload: MarketplaceReportSubmit, user: ActiveUser
) -> DetailResponse:
    """Flag an item for moderator review (one open report per user per item)."""
    if await marketplace_service.get_item(item_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        )
    await moderation_service.submit_report(
        user.id, ReportTarget.ITEM, item_id, payload.reason, payload.note
    )
    return DetailResponse(detail="Report submitted for review. Thank you.")


@router.post(
    "/reviews/{review_id}/report",
    response_model=DetailResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_write_rate_limit],
)
async def report_review(
    review_id: str, payload: MarketplaceReportSubmit, user: ActiveUser
) -> DetailResponse:
    """Flag a review for moderator review (one open report per user per review)."""
    if not await marketplace_service.review_exists(review_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found."
        )
    await moderation_service.submit_report(
        user.id, ReportTarget.REVIEW, review_id, payload.reason, payload.note
    )
    return DetailResponse(detail="Report submitted for review. Thank you.")
