"""Security primitives: password hashing, JWT, and BYOK key encryption.

- Passwords are hashed with Argon2.
- Access/refresh tokens are signed JWTs.
- BYOK API keys are encrypted at rest with AES-256-GCM. Plaintext keys are
  never logged, stored, or returned to the frontend (CLAUDE.md §9.1).
"""

from __future__ import annotations

import base64
import binascii
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# --- Password hashing -----------------------------------------------------

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2 hash for the given plaintext password."""
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against an Argon2 hash."""
    try:
        return _password_hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


# --- JWT ------------------------------------------------------------------

TokenType = Literal["access", "refresh"]


def create_token(
    subject: str,
    token_type: TokenType,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT for the given subject (user id)."""
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_expire_days)
        )
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(
    token: str, *, expected_type: TokenType | None = None
) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises `jwt.InvalidTokenError` (or subclass) if invalid/expired or if the
    token type does not match `expected_type`.
    """
    payload: dict[str, Any] = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


# --- BYOK API-key encryption (AES-256-GCM) --------------------------------

_NONCE_BYTES = 12  # 96-bit nonce recommended for GCM
_KEY_BYTES = 32  # AES-256


def _load_master_key() -> bytes:
    """Decode the 32-byte AES master key from config (base64 or hex)."""
    raw = settings.api_key_master_key.strip()
    # Try base64 first, then hex.
    for decoder in (base64.b64decode, binascii.unhexlify):
        try:
            key = decoder(raw)
        except (binascii.Error, ValueError):
            continue
        if len(key) == _KEY_BYTES:
            return key
    # Fall back to UTF-8 bytes (must still be exactly 32 bytes).
    key = raw.encode("utf-8")
    if len(key) != _KEY_BYTES:
        raise ValueError(
            "API_KEY_MASTER_KEY must decode to 32 bytes (base64/hex/utf-8)."
        )
    return key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret with AES-256-GCM; return base64(nonce || ciphertext)."""
    key = _load_master_key()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Reverse `encrypt_secret`. Raises on tampering (GCM auth failure)."""
    key = _load_master_key()
    blob = base64.b64decode(token)
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_secret(plaintext: str) -> str:
    """Return a display-safe masked hint (last 4 chars) — never the full key."""
    if len(plaintext) <= 4:
        return "****"
    return f"****{plaintext[-4:]}"
