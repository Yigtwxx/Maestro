"""Operator-alert channel seam.

Mirrors the email and payment adapter patterns: adding a delivery channel --
PagerDuty, ntfy, a pager gateway -- means adding one adapter module, not editing
the code that decides an alert should fire. Both shipped channels degrade
safely: with neither configured, ``alert_service.send_alert`` is a no-op that
makes no network call at all.

Alerts are *operator*-facing, which is the one thing that distinguishes them
from every other outbound message in this codebase. They name the dependency
that failed -- something ``/health/ready`` deliberately withholds from an
anonymous caller -- because the recipient is the person who has to fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(slots=True, frozen=True)
class Alert:
    """One operator-facing alert.

    ``summary`` and every value in ``details`` pass through
    ``alert_service.redact`` before any channel sees them, so a call site
    cannot leak a credential by interpolating a config value.
    """

    kind: str
    severity: str
    title: str
    summary: str
    fired_at: datetime
    details: dict[str, str] = field(default_factory=dict)


class AlertError(RuntimeError):
    """Raised when a channel definitively fails to deliver an alert."""


class AlertChannel(Protocol):
    """Interface every operator-alert adapter must implement."""

    name: str

    async def send(self, alert: Alert) -> None:
        """Deliver one alert. Raises AlertError on failure."""
        ...
