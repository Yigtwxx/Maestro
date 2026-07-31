"""Per-account sign-in throttling: the axis `rate_limit` cannot cover.

A rate-limit bucket is keyed by *caller identity* — the JWT subject, or the
client IP on an unauthenticated route. `/login` is unauthenticated, so its
bucket is per-IP, and that is exactly the wrong axis for credential stuffing: a
run spread over a botnet spends one or two attempts per address against the
target account and never comes near the per-IP ceiling. The account itself has
no counter at all, so guesses against one address are effectively unbounded.

This module counts the other axis — failed attempts against one account,
whatever address they arrive from — over the same sliding-window buckets the
limiter already owns, so Redis, the in-memory fallback and the breaker are
shared rather than duplicated.

Only failures are recorded and a success clears the record, so a user who
mistypes twice and then gets it right is never closer to a block than someone
who signed in first try.

**Accepted trade-off.** An attacker who knows an address can spend the budget on
deliberately wrong passwords and keep its owner out for the rest of the window.
That is the standard cost of account-scoped throttling, and it is bounded here:
the block is temporary, never an administrative lock; it cannot be extended past
one window, because a bucket at its ceiling stops recording (further failures
add nothing, so the block still lifts when the *oldest* failure ages out); and
password reset stays open throughout, since it is keyed by an emailed token
rather than by these counters. Weighed against unbounded distributed guessing
against every account at once, a self-healing 15-minute lockout is the cheaper
failure.

The subject is hashed into the key: an address is PII and a bucket key travels
through Redis monitoring, `SCAN` output and support sessions that the address
itself should not.

Like every throttle here, this is disabled by `RATE_LIMIT_ENABLED=false` — a
development escape hatch that production refuses to boot with (CLAUDE.md §9.12).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import ceil

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.constants import (
    LOGIN_FAILURE_BUDGET,
    MFA_FAILURE_BUDGET,
    RATE_LIMIT_KEY_PREFIX,
    RateLimitTier,
)
from app.utils.rate_limiter import limiter

# Deliberately not the generic "slow down" line: this one tells a locked-out
# user what actually happened and that waiting fixes it. It leaks nothing about
# whether the address exists — an unknown address is throttled identically,
# which is what keeps the endpoint from becoming an enumeration oracle.
THROTTLE_DETAIL = (
    "Too many failed sign-in attempts for this account. "
    "Try again later, or reset your password."
)

# 32 hex chars of SHA-256. Not a secret-keyed MAC: the goal is to keep addresses
# out of key listings, not to withstand an attacker who already holds the Redis
# instance — at which point the session tokens in it are the bigger prize.
_DIGEST_CHARS = 32


@dataclass(frozen=True, slots=True)
class AttemptGuard:
    """Counts failed attempts against one subject under `budget`."""

    budget: RateLimitTier

    async def enforce(self, subject: str) -> None:
        """Reject with 429 when `subject` has spent its failure budget.

        Called *before* the credential is checked, so a blocked account costs
        neither an Argon2 verification nor a TOTP comparison. The corollary is
        that a correct password presented during a block is refused too; that
        is the point of the block, not an oversight.
        """
        if not settings.rate_limit_enabled:
            return
        state = await limiter.count(self._key(subject), self.budget)
        if state.count >= self.budget.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=THROTTLE_DETAIL,
                headers={"Retry-After": str(max(1, ceil(state.retry_after)))},
            )

    async def record_failure(self, subject: str) -> None:
        """Charge one failed attempt against `subject`."""
        if not settings.rate_limit_enabled:
            return
        await limiter.hit(self._key(subject), self.budget)

    async def clear(self, subject: str) -> None:
        """Forget `subject`'s failures after a successful attempt."""
        if not settings.rate_limit_enabled:
            return
        await limiter.clear(self._key(subject))

    def _key(self, subject: str) -> str:
        digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
        return f"{RATE_LIMIT_KEY_PREFIX}:{self.budget.name}:{digest}"


# Keyed by the submitted address, normalised but *not* checked against the
# users table: throttling only known accounts would answer 429 for one and 401
# for the other, turning the block itself into an existence oracle.
password = AttemptGuard(LOGIN_FAILURE_BUDGET)

# Keyed by user id — reaching the second factor already resolved the account.
mfa = AttemptGuard(MFA_FAILURE_BUDGET)
