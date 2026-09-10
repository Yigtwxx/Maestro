"""The route-layer half of the SSRF guard, shared by the two features that need it.

``url_guard`` splits deliberately: ``validate_url_shape`` is sync and DNS-free
so a Pydantic validator can run it, and ``check_public_url`` resolves, so it has
to be awaited from a route. Two features now register a user-supplied host —
custom API tools and MCP servers — and a third (plugin manifest import) is
coming. Copying the same eight lines a third time is how "three url_guard calls,
identically" stops being literally true.

Registration is never the only gate. Both services re-check at call time,
because a record outlives its validation and the DNS for a host the user owns is
theirs to change afterwards.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import settings
from app.utils.url_guard import check_public_url


async def reject_private_host(url: str) -> None:
    """Refuse a host that does not resolve to a globally routable address.

    Honours ``settings.llm_ssrf_guard_enabled`` for the reason
    ``custom_api_service`` gives: obeying it in one place but not the other
    would make a host registrable and then silently unusable.
    """
    if not settings.llm_ssrf_guard_enabled:
        return
    reason = await check_public_url(url)
    if reason is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Endpoint rejected: {reason}.",
        )
