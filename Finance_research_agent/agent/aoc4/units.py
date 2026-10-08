"""Unit detection, scale conversion, INR display helpers."""

from __future__ import annotations

import re
from decimal import Decimal


UNIT_FACTORS: dict[str, int] = {
    "actual": 1,
    "thousand": 10**3,
    "lakh": 10**5,
    "million": 10**6,
    "crore": 10**7,
}


def detect_unit(header_text: str) -> str | None:
    """Detect the declared unit from statement header text.

    Examples:
        ``(₹ in Lakhs)`` → ``"lakh"``
        ``(Rs. in crore)`` → ``"crore"``
        ``(INR in Millions)`` → ``"million"``
        ``(Amount in ₹ '000)`` → ``"thousand"``
        ``Amount in Rupees`` → ``"actual"``
    """
    text = header_text.lower()

    if "'000" in text or "in 000" in text or "thousands" in text:
        return "thousand"
    if "lakh" in text or "lac" in text:
        return "lakh"
    if "crore" in text or "'cr" in text:
        return "crore"
    if "million" in text or "mn" in text:
        return "million"
    if "amount in rupees" in text or "₹ only" in text or "in ₹" in text:
        return "actual"

    return None


def scale_to_absolute(value: Decimal, unit: str) -> Decimal:
    """Multiply a value by its declared scale factor → absolute INR."""
    factor = UNIT_FACTORS.get(unit, 1)
    return value * Decimal(str(factor))


def scale_from_absolute(value: Decimal, unit: str) -> Decimal:
    """Divide absolute INR by its scale factor → display value."""
    factor = UNIT_FACTORS.get(unit, 1)
    if factor == 0:
        return value
    return value / Decimal(str(factor))
