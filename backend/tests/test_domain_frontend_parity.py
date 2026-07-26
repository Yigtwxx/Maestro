"""Backend domain catalog must stay in sync with the frontend mirrors.

The frontend hardcodes the domain list (``AGENT_DOMAINS``) and the UI copy
map (``AGENT_LOCALE``). These tests parse those TypeScript files
textually and compare them against ``DOMAIN_CATALOG`` so a forgotten
frontend entry fails CI instead of surfacing as a broken UI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.registry import DOMAIN_CATALOG
from app.core.constants import CONNECTED_TOOL_IDS

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
    """Extract {domain_id: {member ids}} from the AGENT_LOCALE literal."""
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


def _parse_core_connected_tools(source: str) -> dict[str, str]:
    match = re.search(
        r"export const SQUAD_CORE_CONNECTED_TOOL: Record<string, string> = \{"
        r"(?P<body>.*?)\};",
        source,
        re.DOTALL,
    )
    assert match, "SQUAD_CORE_CONNECTED_TOOL map not found in constants.ts"
    return dict(re.findall(r"(\w+): '([a-z_]+)'", match.group("body")))


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


def test_frontend_core_connected_tool_map_matches_catalog():
    """A squad whose first declared tool is connected is built around that API.

    The catalog card labels that tool 'required' (a keyless one excepted), so
    the map must not drift from the backend tool tuples.
    """
    source = _read_frontend_file("constants.ts")
    frontend_map = _parse_core_connected_tools(source)
    backend_map = {
        entry.id: entry.tools[0]
        for entry in DOMAIN_CATALOG
        if entry.tools and entry.tools[0] in CONNECTED_TOOL_IDS
    }
    assert frontend_map == backend_map, (
        f"SQUAD_CORE_CONNECTED_TOOL mismatch: frontend={frontend_map}, "
        f"backend={backend_map}"
    )
