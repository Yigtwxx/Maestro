"""Does this domain accept mail at all?

Catches typos (`gmial.com`) and parked domains. It is **not** an abuse control
and does not pretend to be one -- every disposable provider has perfectly good
MX records. What it protects is sender reputation: a hard bounce is charged
against the sending domain, and that begins to matter the moment a real sender
and the verification gate are switched on together.

Two properties are load-bearing:

* **Fail open.** Any DNS error -- timeout, SERVFAIL, no nameserver -- admits the
  address. A resolver outage taking registration down with it would be a far
  worse failure than the typos this catches.
* **Implicit MX.** A domain with an address record and no MX still receives mail
  (RFC 5321 §5.1). Skipping that fallback would refuse a whole class of small
  legitimate domains.

dnspython is already in the lock as a transitive dependency of
`email-validator`; `requirements.in` names it explicitly because this imports it
directly. The async resolver is used rather than the blocking one so a slow
nameserver cannot stall the event loop.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.resolver

from app.core.config import settings
from app.core.constants import (
    MX_CACHE_MAX_ENTRIES,
    MX_CACHE_TTL_SECONDS,
    MX_LOOKUP_TIMEOUT_SECONDS,
)
from app.utils.email_identity import domain_of

logger = logging.getLogger(__name__)

# domain -> (expires_at_monotonic, deliverable). Process-local: several workers
# each resolve a domain once, which is a rounding error against the saving.
_cache: dict[str, tuple[float, bool]] = {}


async def has_mx(email: str) -> bool:
    """Report whether ``email``'s domain can receive mail.

    Returns True whenever the answer is unknown -- see the module docstring.
    """
    if not settings.email_mx_check_enabled:
        return True
    domain = domain_of(email)
    if not domain:
        return True
    cached = _cache.get(domain)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    try:
        deliverable = await _lookup(domain)
    except dns.exception.DNSException as exc:
        # Deliberately not cached: extending one blip across the whole TTL
        # would turn a transient resolver hiccup into an hour of missing checks.
        # The exception class is logged, never the domain: a bucket key travels
        # through monitoring output the same way `login_throttle` warns about
        # (CLAUDE.md §8), and a domain is PII-adjacent for the same reason.
        logger.warning(
            "MX lookup is failing open (%s); resolver may be degraded",
            type(exc).__name__,
        )
        return True
    if len(_cache) >= MX_CACHE_MAX_ENTRIES:
        # A flush, not LRU eviction: this cache is fed by an unauthenticated
        # endpoint, so the simplest bound that cannot itself become a target is
        # best. A cold cache costs one extra lookup per domain; LRU bookkeeping
        # would add complexity to a structure an attacker can already fill.
        _cache.clear()
    _cache[domain] = (time.monotonic() + MX_CACHE_TTL_SECONDS, deliverable)
    return deliverable


def reset_cache() -> None:
    """Drop every cached answer. For tests; the cache is process-global."""
    _cache.clear()


async def _lookup(domain: str) -> bool:
    """Resolve MX, falling back to the implicit-MX address record.

    Raises ``dns.exception.DNSException`` on anything that is not a definitive
    answer, so the caller can tell "no such domain" from "the resolver is down".
    """
    try:
        answers = await _resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        pass
    else:
        return bool(answers)
    try:
        return bool(await _resolve(domain, "A"))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False


async def _resolve(domain: str, record_type: str) -> Any:
    """The single DNS seam, so tests replace one function."""
    return await dns.asyncresolver.resolve(
        domain, record_type, lifetime=MX_LOOKUP_TIMEOUT_SECONDS
    )
