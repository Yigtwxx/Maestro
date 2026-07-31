"""Per-recipient outbound mail budget.

`rate_limit` keys by *caller identity* -- the client IP on an unauthenticated
route, the JWT subject on an authenticated one. Four endpoints let the caller
choose who receives the mail, so a caller's bucket says nothing about how much
mail any one inbox is taking:

* `POST /auth/register` and `POST /auth/forgot-password` are unauthenticated and
  carry a target address in the body. A run spread over a botnet stays under the
  per-IP ceiling while mailing one victim without bound.
* `POST /users/me/email` takes an *arbitrary* `new_email` behind a session, so a
  single account is a mail cannon aimed at any address the attacker chooses.
  This is the sharpest of the four -- it costs one account to set up, and it is
  also the only one that can mail an address holding no account at all.
* `POST /auth/resend-verification` mails only the caller's own address, so the
  exposure is to sender reputation and outbound volume rather than to a third
  party. It shares the budget because there is no reason to exempt it.

This module counts the axis those miss -- sends per *recipient*, whatever caller
asked for them -- over the same sliding-window buckets `rate_limiter` already
owns, so Redis, the in-memory fallback and the breaker are shared rather than
duplicated. It is the sibling of `utils.login_throttle`, which does the same for
the account axis of `/login`.

Two differences from `login_throttle.AttemptGuard`:

* It returns a bool instead of raising 429. The caller answers with the
  endpoint's normal fixed body, because `/register` and `/forgot-password` are
  built so their response reveals nothing -- a 429 for one address and a 202 for
  another would hand back exactly the oracle they close.
* It counts *every* send rather than only failures. The resource being protected
  is the recipient's inbox, and a wanted message consumes it just as an unwanted
  one does.

**Accepted trade-off.** An attacker can spend a victim's budget to delay their
password-reset mail for the rest of the window. Bounded the way `login_throttle`
bounds its equivalent: the window is short, a bucket at its ceiling stops
recording so the block cannot be extended, and nothing about the account itself
changes. Weighed against an unbounded flood at any address, an hour of delay is
the cheaper failure.

The recipient is hashed into the key: an address is PII and a bucket key travels
through Redis monitoring, `SCAN` output and support sessions that the address
itself should not.

Like every throttle here, this is disabled by `RATE_LIMIT_ENABLED=false` -- a
development escape hatch production refuses to boot with (CLAUDE.md §9.12).
"""

from __future__ import annotations

import hashlib

from app.core.config import settings
from app.core.constants import MAIL_SEND_BUDGET, RATE_LIMIT_KEY_PREFIX
from app.core.metrics import metrics
from app.utils.rate_limiter import limiter

# 32 hex chars of SHA-256, matching `login_throttle`. Not a secret-keyed MAC:
# the goal is keeping addresses out of key listings, not withstanding an
# attacker who already holds the Redis instance.
_DIGEST_CHARS = 32

_REJECT_REASON = "mail_budget"


async def allow(recipient: str) -> bool:
    """Charge one send against `recipient` and report whether it may proceed.

    Records as a side effect, so call this exactly once per intended send and
    only where a message would otherwise go out. A caller that checks without
    sending burns a real user's budget.

    Returns True when the send may proceed, False when the recipient's window is
    full. On False the caller must still answer with its normal response body --
    see the module docstring.
    """
    if not settings.rate_limit_enabled:
        return True
    result = await limiter.hit(_key(recipient), MAIL_SEND_BUDGET)
    if not result.allowed:
        metrics.record_abuse_rejection(_REJECT_REASON)
    return result.allowed


def _key(recipient: str) -> str:
    """Bucket key for one recipient, normalised and hashed."""
    digest = hashlib.sha256(recipient.strip().lower().encode("utf-8")).hexdigest()
    return f"{RATE_LIMIT_KEY_PREFIX}:{MAIL_SEND_BUDGET.name}:{digest[:_DIGEST_CHARS]}"
