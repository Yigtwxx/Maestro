"""Backend domain catalog must stay in sync with the frontend mirrors.

The frontend hardcodes the domain list (``AGENT_DOMAINS``) and the Turkish
locale map (``AGENT_LOCALE_TR``). These tests parse those TypeScript files
textually and compare them against ``DOMAIN_CATALOG`` so a forgotten
frontend entry fails CI instead of surfacing as a broken UI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.registry import DOMAIN_CATALOG

_FRONTEND_LIB = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib"


def _read_frontend_file(name: str) -> str:
    path = _FRONTEND_LIB / name
    if not path.is_file():
        pytest.skip(f"frontend file not available: {path}")
    return path.read_text(encoding="utf-8")


def _parse_agent_domains(source: str) -> list[str]:
    match = re.search(
        r"export const AGENT_DOMAINS = \[(?P<body>.*?)\] as const",
        source,
        re.DOTALL,
    )
    assert match, "AGENT_DOMAINS array not found in constants.ts"
    return re.findall(r"'([a-z_]+)'", match.group("body"))


def _parse_locale_teams(source: str) -> dict[str, set[str]]:
    """Extract {domain_id: {member ids}} from the AGENT_LOCALE_TR literal."""
    domains: dict[str, set[str]] = {}
    starts = [
        (m.start(), m.group(1))
        for m in re.finditer(r"^  ([a-z_]+): \{", source, re.MULTILINE)
    ]
    for index, (offset, domain_id) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(source)
        block = source[offset:end]
        members = set(re.findall(r"^      ([a-z_]+): \{", block, re.MULTILINE))
        domains[domain_id] = members
    return domains


def test_frontend_agent_domains_match_catalog_ids_and_order():
    source = _read_frontend_file("constants.ts")
    frontend_domains = _parse_agent_domains(source)
    backend_domains = [entry.id for entry in DOMAIN_CATALOG]
    assert frontend_domains == backend_domains, (
        f"AGENT_DOMAINS mismatch: frontend={frontend_domains}, "
        f"backend={backend_domains}"
    )


def test_frontend_locale_covers_every_domain_and_member():
    source = _read_frontend_file("agent-locale.ts")
    locale_teams = _parse_locale_teams(source)
    for entry in DOMAIN_CATALOG:
        assert entry.id in locale_teams, f"locale missing domain: {entry.id}"
        member_ids = {member.id for member in entry.team}
        missing = member_ids - locale_teams[entry.id]
        assert not missing, f"locale missing members for {entry.id}: {missing}"
