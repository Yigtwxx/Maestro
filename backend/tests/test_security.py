"""Unit tests for security primitives."""

from __future__ import annotations

import jwt
import pytest
from cryptography.exceptions import InvalidTag

from app.core.security import (
    create_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    mask_secret,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_aes_gcm_roundtrip():
    plaintext = "sk-super-secret-api-key-1234"
    token = encrypt_secret(plaintext)
    assert token != plaintext
    assert decrypt_secret(token) == plaintext


def test_aes_gcm_detects_tampering():
    token = encrypt_secret("value")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(InvalidTag):
        decrypt_secret(tampered)


def test_mask_secret_hides_body():
    assert mask_secret("sk-abcdef1234") == "****1234"
    assert mask_secret("ab") == "****"


def test_jwt_roundtrip_and_type_check():
    token = create_token("user-123", "access")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="refresh")


def test_jwt_extra_claims_roundtrip():
    """Rotation rides on jti/fam claims carried through ``extra_claims``."""
    token = create_token(
        "user-123", "refresh", extra_claims={"jti": "abc", "fam": "xyz"}
    )
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "user-123"
    assert payload["jti"] == "abc"
    assert payload["fam"] == "xyz"
