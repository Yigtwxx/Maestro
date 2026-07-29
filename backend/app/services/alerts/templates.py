"""Alert bodies. Copy lives here so the watchdog stays pure decision logic.

These name the failing dependency on purpose. `/health/ready` withholds that
from an anonymous caller because it is free reconnaissance (CLAUDE.md §8), but
an alert is delivered to a channel the operator configured with their own
credential -- the recipient is the person who has to go restart the thing. The
same reasoning is why the reasoning is written down here: "it names mongo" must
read as a decision, not as an oversight.

Nothing is imported from ``services/email/templates.py``. An operator page is a
different audience from a user's verification mail and should not inherit its
voice or its sign-off.
"""

from __future__ import annotations

from collections.abc import Mapping

_STYLE_BODY = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    "font-size:15px;line-height:1.6;color:#111"
)
_STYLE_FINE = "font-size:13px;color:#666"
_STYLE_TABLE = "border-collapse:collapse;font-size:14px;margin:12px 0"
_STYLE_CELL = "padding:4px 12px 4px 0;vertical-align:top"


def _rows(details: Mapping[str, str]) -> str:
    """Render the details map as HTML table rows."""
    return "".join(
        f'<tr><td style="{_STYLE_CELL}"><strong>{key}</strong></td>'
        f'<td style="{_STYLE_CELL}">{value}</td></tr>'
        for key, value in details.items()
    )


def _html(summary: str, details: Mapping[str, str]) -> str:
    """Wrap a summary and its details in the shared operator-mail shell."""
    return (
        f'<div style="{_STYLE_BODY}">'
        f"<p>{summary}</p>"
        f'<table style="{_STYLE_TABLE}">{_rows(details)}</table>'
        f'<p style="{_STYLE_FINE}">Maestro operator alert. '
        f"Configure or silence these with ALERT_WEBHOOK_URL / ALERT_EMAIL_TO.</p>"
        f"</div>"
    )


def _text(summary: str, details: Mapping[str, str]) -> str:
    """Plain-text rendering, also used verbatim as the webhook body."""
    lines = [summary, ""]
    lines.extend(f"{key}: {value}" for key, value in details.items())
    return "\n".join(lines)


def render(summary: str, details: Mapping[str, str]) -> tuple[str, str]:
    """``(html, text)`` for one alert body."""
    return _html(summary, details), _text(summary, details)


def _failed(checks: Mapping[str, str]) -> list[str]:
    """Names of the dependencies that errored, in a stable order."""
    return sorted(name for name, status in checks.items() if status == "error")


def readiness_degraded(
    checks: Mapping[str, str], *, failures: int
) -> tuple[str, str, dict[str, str]]:
    """``(title, summary, details)`` for a dependency outage."""
    failed = _failed(checks)
    named = ", ".join(failed) if failed else "an unnamed dependency"
    title = f"Maestro is degraded: {named}"
    summary = (
        f"The readiness probe failed {failures} consecutive times. "
        f"Requests that touch {named} will fail until it recovers."
    )
    details = {
        "status": "degraded",
        "failing": named,
        "checks": ", ".join(
            f"{name}={status}" for name, status in sorted(checks.items())
        ),
    }
    return title, summary, details


def readiness_recovered(
    checks: Mapping[str, str], *, downtime_seconds: float
) -> tuple[str, str, dict[str, str]]:
    """``(title, summary, details)`` for a recovery from degraded."""
    title = "Maestro has recovered"
    summary = (
        f"Every backing service is answering again after "
        f"{downtime_seconds:.0f}s degraded."
    )
    details = {
        "status": "ready",
        "downtime_seconds": f"{downtime_seconds:.0f}",
        "checks": ", ".join(
            f"{name}={status}" for name, status in sorted(checks.items())
        ),
    }
    return title, summary, details


def error_rate_exceeded(
    *,
    total: int,
    errors: int,
    rate: float,
    window_seconds: float,
    threshold: float,
) -> tuple[str, str, dict[str, str]]:
    """``(title, summary, details)`` for a 5xx rate above the threshold."""
    title = f"Maestro is erroring: {rate:.1%} of requests are 5xx"
    summary = (
        f"{errors} of the last {total} requests returned a server error over "
        f"the past {window_seconds:.0f}s, above the {threshold:.1%} threshold. "
        f"Counts are per worker; health probes are excluded."
    )
    details = {
        "server_errors": str(errors),
        "requests": str(total),
        "rate": f"{rate:.2%}",
        "threshold": f"{threshold:.2%}",
        "window_seconds": f"{window_seconds:.0f}",
    }
    return title, summary, details
