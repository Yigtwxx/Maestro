"""Admin / moderation endpoints (CLAUDE.md §9 — marketplace abuse control).

Every route is gated by ``AdminUser`` and carries an explicit rate-limit
dependency (CLAUDE.md §9.4). This is the only surface that exposes content
author/reporter attribution, so the guard is non-negotiable.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.core.constants import (
    ADMIN_PAGE_SIZE_DEFAULT,
    ADMIN_PAGE_SIZE_MAX,
    RATE_LIMIT_READ,
    RATE_LIMIT_WRITE,
)
from app.core.deps import AdminUser, DbSession
from app.schemas.admin import (
    AdminMarketplaceItem,
    AdminReview,
    AdminUserDetail,
    AdminUserRow,
    AuditEntry,
    ItemStatusRequest,
    ModerationReasonRequest,
    OverviewStats,
    ReportRow,
    ResolveRequest,
    ReviewHideRequest,
    RoleRequest,
)
from app.schemas.auth import DetailResponse
from app.services import marketplace_service, moderation_service
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/admin", tags=["admin"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="admin")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="admin")

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


# --- Overview ---


@router.get("/overview", response_model=OverviewStats, dependencies=[_read_rate_limit])
async def overview(admin: AdminUser, db: DbSession) -> dict:
    """Platform-wide moderation counters."""
    return await moderation_service.overview(db)


# --- Users ---


@router.get(
    "/users", response_model=list[AdminUserRow], dependencies=[_read_rate_limit]
)
async def list_users(
    admin: AdminUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=320),
    limit: int = Query(default=ADMIN_PAGE_SIZE_DEFAULT, ge=1, le=ADMIN_PAGE_SIZE_MAX),
    offset: int = Query(default=0, ge=0),
) -> list:
    """List users, optionally filtered by an email substring."""
    return await moderation_service.list_users(db, query=q, limit=limit, offset=offset)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    dependencies=[_read_rate_limit],
)
async def get_user(admin: AdminUser, db: DbSession, user_id: uuid.UUID) -> dict:
    """A user plus their moderation-relevant content counts."""
    detail = await moderation_service.get_user_detail(db, user_id)
    if detail is None:
        raise _NOT_FOUND
    return detail


@router.post(
    "/users/{user_id}/suspend",
    response_model=AdminUserRow,
    dependencies=[_write_rate_limit],
)
async def suspend_user(
    admin: AdminUser,
    db: DbSession,
    user_id: uuid.UUID,
    payload: ModerationReasonRequest,
) -> object:
    """Lock an abusive account out of the product surface."""
    user = await moderation_service.suspend_user(
        db, user_id, moderator=admin, reason=payload.reason
    )
    if user is None:
        raise _NOT_FOUND
    return user


@router.post(
    "/users/{user_id}/unsuspend",
    response_model=AdminUserRow,
    dependencies=[_write_rate_limit],
)
async def unsuspend_user(admin: AdminUser, db: DbSession, user_id: uuid.UUID) -> object:
    """Lift an account suspension."""
    user = await moderation_service.unsuspend_user(db, user_id, moderator=admin)
    if user is None:
        raise _NOT_FOUND
    return user


@router.post(
    "/users/{user_id}/role",
    response_model=AdminUserRow,
    dependencies=[_write_rate_limit],
)
async def set_user_role(
    admin: AdminUser, db: DbSession, user_id: uuid.UUID, payload: RoleRequest
) -> object:
    """Promote or demote a user (admin <-> user)."""
    user = await moderation_service.set_user_role(
        db, user_id, payload.role, moderator=admin
    )
    if user is None:
        raise _NOT_FOUND
    return user


# --- Marketplace items ---


@router.get(
    "/marketplace/items",
    response_model=list[AdminMarketplaceItem],
    dependencies=[_read_rate_limit],
)
async def list_items(
    admin: AdminUser,
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=ADMIN_PAGE_SIZE_DEFAULT, ge=1, le=ADMIN_PAGE_SIZE_MAX),
    offset: int = Query(default=0, ge=0),
) -> list:
    """Every item (any status), with author attribution."""
    return await marketplace_service.admin_list_items(
        status=status_filter, limit=limit, offset=offset
    )


@router.post(
    "/marketplace/items/{item_id}/status",
    response_model=AdminMarketplaceItem,
    dependencies=[_write_rate_limit],
)
async def set_item_status(
    admin: AdminUser, item_id: str, payload: ItemStatusRequest
) -> dict:
    """Hide, remove, or reinstate a marketplace item."""
    item = await moderation_service.set_item_status(
        item_id, payload.status, moderator_id=admin.id, reason=payload.reason
    )
    if item is None:
        raise _NOT_FOUND
    return item


@router.get(
    "/marketplace/items/{item_id}/reviews",
    response_model=list[AdminReview],
    dependencies=[_read_rate_limit],
)
async def list_item_reviews(admin: AdminUser, item_id: str) -> list:
    """All reviews of an item (including hidden), with reviewer attribution."""
    return await marketplace_service.admin_list_reviews(item_id)


@router.post(
    "/marketplace/reviews/{review_id}/hide",
    response_model=AdminReview,
    dependencies=[_write_rate_limit],
)
async def hide_review(
    admin: AdminUser, review_id: str, payload: ReviewHideRequest
) -> dict:
    """Hide or unhide a review."""
    review = await moderation_service.set_review_hidden(
        review_id, payload.hidden, moderator_id=admin.id, reason=payload.reason
    )
    if review is None:
        raise _NOT_FOUND
    return review


# --- Custom agent take-down ---


@router.delete(
    "/agents/{agent_id}",
    response_model=DetailResponse,
    dependencies=[_write_rate_limit],
)
async def delete_agent(
    admin: AdminUser,
    agent_id: str,
    reason: str | None = Query(default=None, max_length=500),
) -> DetailResponse:
    """Take down an abusive custom agent (cross-user)."""
    deleted = await moderation_service.delete_agent(
        agent_id, moderator_id=admin.id, reason=reason
    )
    if not deleted:
        raise _NOT_FOUND
    return DetailResponse(detail="Agent removed.")


# --- Reports ---


@router.get("/reports", response_model=list[ReportRow], dependencies=[_read_rate_limit])
async def list_reports(
    admin: AdminUser,
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=ADMIN_PAGE_SIZE_DEFAULT, ge=1, le=ADMIN_PAGE_SIZE_MAX),
    offset: int = Query(default=0, ge=0),
) -> list:
    """The moderation report queue, newest first (optionally by status)."""
    return await moderation_service.list_reports(
        report_status=status_filter, limit=limit, offset=offset
    )


@router.post(
    "/reports/{report_id}/resolve",
    response_model=ReportRow,
    dependencies=[_write_rate_limit],
)
async def resolve_report(
    admin: AdminUser, report_id: str, payload: ResolveRequest
) -> dict:
    """Close a report as resolved or dismissed."""
    report = await moderation_service.resolve_report(
        report_id, moderator_id=admin.id, resolution=payload.resolution
    )
    if report is None:
        raise _NOT_FOUND
    return report


# --- Audit ---


@router.get("/audit", response_model=list[AuditEntry], dependencies=[_read_rate_limit])
async def list_audit(
    admin: AdminUser,
    limit: int = Query(default=ADMIN_PAGE_SIZE_DEFAULT, ge=1, le=ADMIN_PAGE_SIZE_MAX),
    offset: int = Query(default=0, ge=0),
) -> list:
    """The moderator action audit trail, most recent first."""
    return await moderation_service.list_actions(limit=limit, offset=offset)
