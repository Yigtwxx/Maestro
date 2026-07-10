"""Marketplace schemas (published agent teams).

Published items are community-shared agent configurations. Every publish runs a
mandatory security scan on the system prompt (CLAUDE.md §9.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MarketplacePublish(BaseModel):
    """Payload to publish an agent team to the marketplace."""

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
