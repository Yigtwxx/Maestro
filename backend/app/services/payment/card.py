"""Card-number helpers: sanitizing, Luhn checksum and scheme detection.

Pure functions, no I/O. Only Visa and Mastercard are accepted.

These operate on the raw PAN. Nothing here logs or persists it -- callers must
keep it in memory only for the duration of a provider call.
"""

from __future__ import annotations

import re
from datetime import date

from app.core.constants import CardBrand

_NON_DIGITS = re.compile(r"[\s-]")
_VISA = re.compile(r"^4\d{12,18}$")
# Mastercard: the legacy 51-55 range plus the 2221-2720 range added in 2017.
_MASTERCARD_LEGACY = re.compile(r"^5[1-5]\d{14}$")
# The 2-series covers BINs 2221-2720 inclusive; the alternation spells out that
# range digit by digit (2221-2229, 2230-2299, 2300-2699, 2700-2719, 2720).
_MASTERCARD_2_SERIES = re.compile(
    r"^2(?:22[1-9]|2[3-9]\d|[3-6]\d\d|7[01]\d|720)\d{12}$"
)

LAST4_LENGTH = 4


def sanitize(number: str) -> str:
    """Strip the spaces and dashes users type into card fields."""
    return _NON_DIGITS.sub("", number)


def luhn_valid(number: str) -> bool:
    """Verify the Luhn (mod-10) checksum of a sanitized card number."""
    if not number.isdigit() or len(number) < 12:
        return False

    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def detect_brand(number: str) -> CardBrand | None:
    """Return the card scheme, or None if it is not one we accept."""
    if _VISA.match(number):
        return CardBrand.VISA
    if _MASTERCARD_LEGACY.match(number) or _MASTERCARD_2_SERIES.match(number):
        return CardBrand.MASTERCARD
    return None


def last4(number: str) -> str:
    """The only part of the PAN that is safe to store."""
    return number[-LAST4_LENGTH:]


def card_not_expired(exp_month: int, exp_year: int, *, now: date) -> bool:
    """A card is valid through the last day of its expiry month."""
    return (exp_year, exp_month) >= (now.year, now.month)
