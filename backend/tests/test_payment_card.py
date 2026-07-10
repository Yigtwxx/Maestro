"""Unit tests for card sanitizing, Luhn validation and scheme detection."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.constants import CardBrand
from app.services.payment import card

_VISA = "4242424242424242"
_MASTERCARD = "5555555555554444"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4242 4242 4242 4242", _VISA),
        ("4242-4242-4242-4242", _VISA),
        (_VISA, _VISA),
    ],
)
def test_sanitize_strips_separators(raw: str, expected: str) -> None:
    assert card.sanitize(raw) == expected, (
        f"Expected {expected}, got {card.sanitize(raw)}"
    )


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (_VISA, True),
        (_MASTERCARD, True),
        ("4000000000000002", True),
        ("4242424242424243", False),  # checksum off by one
        ("5555555555554445", False),
        ("4242", False),  # too short
        ("42424242424242ab", False),  # non-numeric
    ],
)
def test_luhn_valid(number: str, expected: bool) -> None:
    assert card.luhn_valid(number) is expected, f"Luhn mismatch for {number}"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (_VISA, CardBrand.VISA),
        ("4111111111111", CardBrand.VISA),  # 13-digit Visa
        (_MASTERCARD, CardBrand.MASTERCARD),
        ("5105105105105100", CardBrand.MASTERCARD),  # 51 range
        ("5599999999999999", CardBrand.MASTERCARD),  # 55 range
        ("2221000000000009", CardBrand.MASTERCARD),  # 2-series lower bound
        ("2720999999999996", CardBrand.MASTERCARD),  # 2-series upper bound
        ("2220999999999999", None),  # just below the 2-series
        ("2721000000000000", None),  # just above the 2-series
        ("6011111111111117", None),  # Discover
        ("340000000000009", None),  # Amex
        ("5011111111111117", None),  # 50 is not Mastercard
    ],
)
def test_detect_brand(number: str, expected: CardBrand | None) -> None:
    assert card.detect_brand(number) is expected, f"Brand mismatch for {number}"


def test_last4_returns_final_four_digits() -> None:
    assert card.last4(_VISA) == "4242", f"Expected 4242, got {card.last4(_VISA)}"


@pytest.mark.parametrize(
    ("exp_month", "exp_year", "expected"),
    [
        (7, 2026, True),  # the current month is still valid
        (8, 2026, True),
        (6, 2026, False),  # last month
        (12, 2025, False),
        (1, 2027, True),
    ],
)
def test_card_not_expired(exp_month: int, exp_year: int, expected: bool) -> None:
    now = date(2026, 7, 15)
    result = card.card_not_expired(exp_month, exp_year, now=now)
    assert result is expected, f"Expected {expected} for {exp_month}/{exp_year}"
