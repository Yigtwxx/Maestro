"""TOTP two-factor auth: enrollment, verification, recovery codes.

The TOTP secret is encrypted at rest with the shared AES master key
(``core.security.encrypt_secret``) and never leaves the server once enrolled.
Recovery codes are stored only as Argon2 hashes and are single-use.
"""

from __future__ import annotations

import io
import secrets
import uuid
from datetime import UTC, datetime

import pyotp
import qrcode
import qrcode.image.svg
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    RECOVERY_CODE_BYTES,
    RECOVERY_CODE_COUNT,
    TOTP_ISSUER,
    TOTP_VALID_WINDOW,
)
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.models.recovery_code import RecoveryCode
from app.models.user import User


def generate_secret() -> str:
    """A fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """The ``otpauth://`` URI an authenticator app scans."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def qr_svg(uri: str) -> str:
    """Render the provisioning URI as inline SVG (no Pillow, no binary asset)."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode("utf-8")


def verify_totp(secret: str, code: str) -> bool:
    """Whether ``code`` is a currently-valid TOTP for ``secret``."""
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=TOTP_VALID_WINDOW)


def _canonical_recovery(code: str) -> str:
    """Normalize a recovery code: alphanumeric, lowercase (dashes/spaces ignored)."""
    return "".join(ch for ch in code.lower() if ch.isalnum())


def _format_recovery(canonical: str) -> str:
    """Display form of a recovery code, grouped for readability (e.g. ab12-cd34)."""
    mid = len(canonical) // 2
    return f"{canonical[:mid]}-{canonical[mid:]}"


async def begin_setup(db: AsyncSession, user: User) -> tuple[str, str]:
    """Generate and store an unconfirmed secret; return (secret, otpauth_uri).

    Storing it with ``totp_enabled`` still False leaves login unaffected until
    the user confirms a code via :func:`enable`. Re-running setup overwrites any
    prior unconfirmed secret.
    """
    secret = generate_secret()
    user.totp_secret = encrypt_secret(secret)
    await db.commit()
    return secret, provisioning_uri(secret, user.email)


async def enable(db: AsyncSession, user: User, code: str) -> list[str]:
    """Confirm the pending secret with a TOTP code and turn 2FA on.

    Returns the plaintext recovery codes (shown once). Raises ValueError if no
    setup is pending or the code is wrong.
    """
    if not user.totp_secret:
        raise ValueError("No two-factor setup is pending.")
    secret = decrypt_secret(user.totp_secret)
    if not verify_totp(secret, code):
        raise ValueError("Invalid authentication code.")

    user.totp_enabled = True
    codes = await _regenerate_recovery_codes(db, user.id)
    await db.commit()
    return codes


async def disable(db: AsyncSession, user: User) -> None:
    """Turn 2FA off: clear the secret and delete all recovery codes."""
    user.totp_enabled = False
    user.totp_secret = None
    await _delete_recovery_codes(db, user.id)
    await db.commit()


async def verify_login(db: AsyncSession, user: User, code: str) -> bool:
    """Second-factor check at login: accept a valid TOTP or a recovery code.

    A redeemed recovery code is consumed (marked used). Commits on a successful
    recovery-code redemption.
    """
    if user.totp_secret and verify_totp(decrypt_secret(user.totp_secret), code):
        return True
    return await _consume_recovery_code(db, user.id, code)


# --- Recovery codes -------------------------------------------------------


async def _regenerate_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Replace a user's recovery codes with a fresh batch; return the plaintext."""
    await _delete_recovery_codes(db, user_id)
    plaintext: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        canonical = secrets.token_hex(RECOVERY_CODE_BYTES)
        plaintext.append(_format_recovery(canonical))
        db.add(RecoveryCode(user_id=user_id, code_hash=hash_password(canonical)))
    return plaintext


async def _delete_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Drop a user's recovery codes in one statement (no commit).

    Bulk DML skips the ORM evaluate pass; callers commit right after, so
    in-session object state does not matter here.
    """
    await db.execute(
        delete(RecoveryCode)
        .where(RecoveryCode.user_id == user_id)
        .execution_options(synchronize_session=False)
    )


async def _consume_recovery_code(
    db: AsyncSession, user_id: uuid.UUID, code: str
) -> bool:
    """Redeem an unused recovery code (single-use). Commits on success."""
    canonical = _canonical_recovery(code)
    if not canonical:
        return False
    result = await db.execute(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user_id,
            RecoveryCode.used_at.is_(None),
        )
    )
    for row in result.scalars():
        if verify_password(canonical, row.code_hash):
            await db.execute(
                update(RecoveryCode)
                .where(RecoveryCode.id == row.id)
                .values(used_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            return True
    return False
