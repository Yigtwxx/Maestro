"""The frontend provider catalog must stay in sync with the backend enum.

Three hand-maintained frontend lists mirror ``LLMProvider``: the string union in
``types/index.ts``, the ``PROVIDERS`` registry in ``lib/providers.ts``, and the
chat/service flags on each registry entry. Nothing else checks them, and the
failure is not a compile error -- a provider missing from ``PROVIDERS`` makes
``PROVIDER_MAP[id]`` undefined and throws in the architect catalog at render
time. These tests parse the TypeScript textually, the same way
``test_domain_frontend_parity`` does, so a forgotten entry fails CI instead.

Deliberately not asserted: ``group``, ``label``, ``hint``, ``docsUrl`` and
``modelPlaceholder``. Those are presentation, and coupling a backend test to
them would turn every copy tweak into a backend failure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.constants import LLM_CHAT_PROVIDERS, SERVICE_PROVIDERS, LLMProvider

_FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read_frontend_file(relative: str) -> str:
    path = _FRONTEND_SRC / relative
    if not path.is_file():
        pytest.skip(f"frontend file not available: {path}")
    return path.read_text(encoding="utf-8")


def _parse_type_union(source: str) -> list[str]:
    match = re.search(
        r"export type LLMProvider =(?P<body>.*?);",
        source,
        re.DOTALL,
    )
    assert match, "LLMProvider union not found in types/index.ts"
    return re.findall(r"'([a-z0-9_]+)'", match.group("body"))


def _parse_provider_entries(source: str) -> list[tuple[str, str]]:
    """Return [(id, entry source)] for every PROVIDERS entry, in order.

    Entries are split on the offsets of their ``id:`` field rather than matched
    as whole object literals: the field sets vary per entry, so an object-shaped
    regex would be fragile.
    """
    block = re.search(
        r"export const PROVIDERS: readonly ProviderMeta\[\] = \["
        r"(?P<body>.*?)\n\] as const;",
        source,
        re.DOTALL,
    )
    assert block, "PROVIDERS array not found in lib/providers.ts"
    body = block.group("body")

    starts = [(m.start(), m.group(1)) for m in re.finditer(r"id: '([a-z0-9_]+)'", body)]
    entries: list[tuple[str, str]] = []
    for index, (offset, provider_id) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(body)
        entries.append((provider_id, body[offset:end]))
    return entries


def test_frontend_type_union_matches_enum_exactly():
    """Compared as an ordered list, so the union stays readable against the enum."""
    frontend = _parse_type_union(_read_frontend_file("types/index.ts"))
    backend = [provider.value for provider in LLMProvider]
    assert frontend == backend, (
        f"LLMProvider union drift: missing={set(backend) - set(frontend)}, "
        f"extra={set(frontend) - set(backend)}"
    )


def test_frontend_registry_covers_every_provider():
    """List comparison also catches a duplicate id.

    A duplicate would collapse silently in ``Object.fromEntries`` when
    PROVIDER_MAP is built, leaving one entry unreachable.
    """
    frontend = [
        provider_id
        for provider_id, _ in _parse_provider_entries(
            _read_frontend_file("lib/providers.ts")
        )
    ]
    backend = [provider.value for provider in LLMProvider]
    assert frontend == backend, (
        f"PROVIDERS drift: missing={set(backend) - set(frontend)}, "
        f"extra={set(frontend) - set(backend)}"
    )


def test_frontend_chat_flag_matches_backend_brains():
    """Catches a brain the UI offers but the task endpoint would reject."""
    entries = _parse_provider_entries(_read_frontend_file("lib/providers.ts"))
    frontend = {pid for pid, entry in entries if "chat: true" in entry}
    backend = {provider.value for provider in LLM_CHAT_PROVIDERS}
    assert frontend == backend, (
        f"chat flag drift: missing={backend - frontend}, extra={frontend - backend}"
    )


def test_frontend_service_category_matches_backend_services():
    entries = _parse_provider_entries(_read_frontend_file("lib/providers.ts"))
    frontend = {pid for pid, entry in entries if "category: 'service'" in entry}
    backend = {provider.value for provider in SERVICE_PROVIDERS}
    assert frontend == backend, (
        f"service category drift: missing={backend - frontend}, "
        f"extra={frontend - backend}"
    )
