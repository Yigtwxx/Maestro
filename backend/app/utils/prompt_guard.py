"""Basic prompt-injection heuristics.

A lightweight first line of defense for user prompts and marketplace system
prompts (CLAUDE.md §9.3). Not a complete solution — pairs with sandboxed
service-layer execution and human review.
"""

from __future__ import annotations

import re

# Bumped whenever the pattern set changes. Stored on a custom agent's
# ``security_scan`` at write time; ``registry.resolve_domain_info`` re-scans at
# execution so a config written under an older scanner is never grandfathered in.
SCANNER_VERSION = 1

# Patterns commonly seen in prompt-injection / jailbreak attempts.
_SUSPICIOUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(above|system)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions)", re.IGNORECASE),
    re.compile(
        r"\b(api[_\s-]?key|secret|password|token)s?\b.*\b(print|show|reveal|leak)\b",
        re.IGNORECASE,
    ),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(dan|developer\s+mode)", re.IGNORECASE),
)


def scan_prompt(text: str) -> list[str]:
    """Return a list of matched suspicious-pattern descriptions (empty = clean)."""
    findings: list[str] = []
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            findings.append(pattern.pattern)
    return findings


def is_suspicious(text: str) -> bool:
    """True if the text matches any known injection pattern."""
    return bool(scan_prompt(text))
