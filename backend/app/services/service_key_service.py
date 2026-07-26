"""Per-user BYOK credentials for non-LLM service integrations.

The ``api_keys`` table has always been able to hold keys for X, GitHub, Google
Maps, Discord, Slack, Telegram and friends — the settings UI writes them and the
schema treats them as a first-class case — but nothing ever read them back. This
module is that missing consumer: it loads and decrypts a user's service keys
once per task run, at the engine edge, so the agent layer receives plain data
and never touches the database or the master key.

That mirrors how ``memory_context`` and the LLM brain key already reach an
agent: resolved at the edge, handed down as a value.

Two contracts matter here:

* **Never raises.** A rotated or corrupt key is logged (provider name only) and
  skipped, exactly like :func:`reconcile._resolve_credentials`. A missing
  service key is not an error condition — it means the tool is withheld and the
  subagent works from ``web_search`` instead (CLAUDE.md §8 stops a task only for
  a missing *brain* key).
* **Never leaks.** :class:`ServiceCredentials` overrides ``__repr__`` so the
  object can appear in a traceback, a log record or a debugger without exposing
  a secret. Do not add a field, a ``__str__`` or a ``dict()`` that undoes this.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.constants import SERVICE_PROVIDERS, LLMProvider
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.api_key import ApiKey

logger = logging.getLogger(__name__)

__all__ = ["ServiceCredentials", "load_service_credentials"]


@dataclass(frozen=True, slots=True)
class ServiceCredentials:
    """Decrypted service keys for one user, keyed by provider value.

    Construct via :func:`load_service_credentials`. The empty instance is the
    normal case for most users and every self-host default, so every consumer
    must treat "no credential" as an ordinary path rather than a failure.
    """

    # provider value (e.g. "github") -> decrypted secret.
    _secrets: dict[str, str] = field(default_factory=dict, repr=False)

    def get(self, provider: LLMProvider | str) -> str | None:
        """Return the decrypted key for a provider, or None if not connected."""
        key = provider.value if isinstance(provider, LLMProvider) else provider
        return self._secrets.get(key)

    def has(self, provider: LLMProvider | str) -> bool:
        """Whether this user has an active key for the provider."""
        return self.get(provider) is not None

    def connected(self) -> frozenset[str]:
        """Provider values this user has connected — safe to log or serialize."""
        return frozenset(self._secrets)

    def __repr__(self) -> str:
        """Render provider names only. The secrets must never be printable."""
        names = ", ".join(sorted(self._secrets))
        return f"ServiceCredentials(connected=[{names}])"

    __str__ = __repr__


EMPTY_CREDENTIALS = ServiceCredentials()


async def load_service_credentials(user_id: uuid.UUID) -> ServiceCredentials:
    """Load and decrypt every active service key for a user. Never raises.

    Ordered newest-first so the result is deterministic: ``api_keys`` carries no
    ``(user_id, provider)`` uniqueness constraint, so a user can hold several
    active rows for the same provider and "which one wins" would otherwise
    depend on row order. The most recently added key wins, which is what a user
    rotating a key expects.
    """
    try:
        async with SessionLocal() as db:
            rows = (
                await db.scalars(
                    select(ApiKey)
                    .where(
                        ApiKey.user_id == user_id,
                        ApiKey.provider.in_([p.value for p in SERVICE_PROVIDERS]),
                        ApiKey.is_active.is_(True),
                    )
                    .order_by(ApiKey.created_at.desc())
                )
            ).all()
    except Exception:  # noqa: BLE001 - a DB hiccup must not fail the task
        logger.warning("Could not load service credentials", exc_info=True)
        return EMPTY_CREDENTIALS

    secrets: dict[str, str] = {}
    for row in rows:
        if row.provider in secrets:  # newest already won
            continue
        try:
            secrets[row.provider] = decrypt_secret(row.encrypted_key)
        except Exception:  # noqa: BLE001 - corrupt/rotated key: skip, don't fail
            # Provider name only. The ciphertext and the exception detail could
            # both narrow an attack on the master key.
            logger.warning("Skipping undecryptable %s service key", row.provider)
    return ServiceCredentials(secrets)
