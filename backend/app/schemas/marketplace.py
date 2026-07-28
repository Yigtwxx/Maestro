"""Marketplace schemas (published agent teams).

Published items are community-shared agent configurations. Every publish runs a
mandatory security scan on the system prompt (CLAUDE.md §9.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import (
    REPORT_NOTE_MAX_LEN,
    REVIEW_COMMENT_MAX_LEN,
    REVIEW_RATING_MAX,
    REVIEW_RATING_MIN,
    ReportReason,
)


class MarketplacePublish(BaseModel):
    """Payload to publish an agent team to the marketplace.

    ``extra="forbid"`` is load-bearing, not tidiness: a published item must not
    be able to carry ``custom_api_tool_ids``. Those name endpoints (and
    encrypted credentials) belonging to the publisher's account, and the field's
    absence here is the first of three layers that keep them from travelling to
    an installer. Silently ignoring the field would leave the invariant true but
    invisible; a 422 says so out loud.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=40)
    system_prompt: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list)


class MarketplaceItemPublic(BaseModel):
    """A published marketplace item, as served to an authenticated user."""

    id: str
    name: str
    description: str
    domain: str
    system_prompt: str
    tools: list[str]
    installs: int
    security_scan: dict[str, Any]
    created_at: datetime
    # Daily install counts over the trend window (oldest first); None until the
    # item has recorded install events — the UI hides the sparkline rather than
    # faking one. Also None on the publish response, which computes no history.
    install_history: list[int] | None = None
    # Denormalized review aggregates, recomputed on every review write. The
    # defaults keep documents published before reviews existed serializable.
    rating_avg: float | None = None
    rating_count: int = 0


class MarketplaceItemPreview(BaseModel):
    """A published item as served to anonymous visitors on the landing page.

    Deliberately narrower than ``MarketplaceItemPublic``: the ``system_prompt``
    is an author's intellectual property and the full ``security_scan`` carries
    the matched injection patterns, so neither leaves the authenticated surface.
    Only the scan's verdict is exposed.
    """

    id: str
    name: str
    description: str
    domain: str
    tools: list[str]
    installs: int
    featured: bool
    author_label: str
    security_scan_status: str
    created_at: datetime
    rating_avg: float | None = None
    rating_count: int = 0


class MarketplaceReviewSubmit(BaseModel):
    """Payload to create or replace the caller's review of an item."""

    rating: int = Field(ge=REVIEW_RATING_MIN, le=REVIEW_RATING_MAX)
    comment: str | None = Field(default=None, max_length=REVIEW_COMMENT_MAX_LEN)


class MarketplaceReviewPublic(BaseModel):
    """A review as served to clients.

    Deliberately carries no author identity: reviewer display names are never
    made public (same policy as ``MARKETPLACE_COMMUNITY_AUTHOR``). ``is_own``
    is computed server-side so the caller can find and edit their review.
    """

    # The review's own id (a random uuid, not identity) — lets a reader flag a
    # specific abusive review.
    id: str
    rating: int
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    is_own: bool = False


class MarketplaceReportSubmit(BaseModel):
    """Payload to flag a marketplace item or review for moderator review."""

    reason: ReportReason
    note: str | None = Field(default=None, max_length=REPORT_NOTE_MAX_LEN)


class MarketplaceReviewList(BaseModel):
    """One page of an item's reviews, newest first."""

    items: list[MarketplaceReviewPublic]
    total: int
    # The caller's review regardless of which page it falls on, so the form
    # can prefill without paging.
    my_review: MarketplaceReviewPublic | None = None
