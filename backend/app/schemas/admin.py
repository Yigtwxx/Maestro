"""Admin / moderation request & response schemas.

Served only behind the admin guard, so these carry attribution (``author_id``,
``reporter_id``, user email) that never leaves the end-user marketplace surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import (
    REPORT_NOTE_MAX_LEN,
    MarketplaceStatus,
    ReportStatus,
    UserRole,
)


class RecentItem(BaseModel):
    """A compact marketplace item row for the overview's recent-publishes list."""

    id: str
    name: str
    domain: str
    author_id: str | None = None
    status: str
    created_at: datetime | None = None


class OverviewStats(BaseModel):
    """Platform-wide moderation counters for the admin dashboard."""

    users_total: int
    admins_total: int
    suspended_total: int
    items_total: int
    items_hidden: int
    items_removed: int
    reviews_total: int
    open_reports: int
    recent_items: list[RecentItem]


class AdminUserRow(BaseModel):
    """A user as shown in the moderation user list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None = None
    role: str
    subscription_tier: str | None = None
    email_verified: bool = False
    suspended_at: datetime | None = None
    deletion_requested_at: datetime | None = None
    created_at: datetime | None = None


class UserContentCounts(BaseModel):
    items: int
    agents: int
    reviews: int


class AdminUserDetail(BaseModel):
    """A user plus their moderation-relevant content counts."""

    user: AdminUserRow
    counts: UserContentCounts


class ModerationReasonRequest(BaseModel):
    """Optional free-text reason attached to a moderation action + audit entry."""

    reason: str | None = Field(default=None, max_length=REPORT_NOTE_MAX_LEN)


class RoleRequest(BaseModel):
    """Promote/demote a user."""

    role: UserRole


class ItemStatusRequest(ModerationReasonRequest):
    """Apply a moderation status to a marketplace item."""

    status: MarketplaceStatus


class ReviewHideRequest(ModerationReasonRequest):
    """Hide or unhide a review."""

    hidden: bool = True


class ResolveRequest(BaseModel):
    """Close a report (resolved or dismissed)."""

    resolution: ReportStatus = ReportStatus.RESOLVED


class AdminMarketplaceItem(BaseModel):
    """A marketplace item with author attribution and moderation metadata."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str = ""
    domain: str = ""
    author_id: str | None = None
    installs: int = 0
    status: str = MarketplaceStatus.PUBLISHED.value
    rating_avg: float | None = None
    rating_count: int = 0
    security_scan: dict[str, Any] | None = None
    moderation: dict[str, Any] | None = None
    created_at: datetime | None = None


class AdminReview(BaseModel):
    """A review with reviewer attribution (moderator view)."""

    model_config = ConfigDict(extra="allow")

    id: str
    item_id: str
    user_id: str
    rating: int
    comment: str | None = None
    hidden: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReportRow(BaseModel):
    """A user-submitted content report in the moderation queue."""

    model_config = ConfigDict(extra="allow")

    id: str
    target_type: str
    target_id: str
    reporter_id: str
    reason: str
    note: str | None = None
    status: str = ReportStatus.OPEN.value
    created_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None


class AuditEntry(BaseModel):
    """One moderator action from the audit trail."""

    model_config = ConfigDict(extra="allow")

    id: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
