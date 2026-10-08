"""Indian number parser — handles lakh/crore grouping, dashes, parentheses, etc."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal


@dataclass
class ParsedNumber:
    value: Decimal | None
    dash_as_zero: bool = False


UNIT_FACTORS: dict[str, int] = {
    "actual": 1,
    "thousand": 10**3,
    "lakh": 10**5,
    "million": 10**6,
    "crore": 10**7,
}


def parse_indian_number(text: str, *, context: str = "money") -> ParsedNumber:
    """Parse an Indian-format number string → ``Decimal``.

    Handles:
    - ``1,23,456.78`` (Indian grouping)
    - ``(1,234.50)`` → negative
    - ``—``, ``–``, ``Nil``, ``NIL`` → zero (dash_as_zero=True)
    - ``₹ 1,234``, ``Rs. 1,234`` → strips currency prefix
    - ``1,234*``, ``1,234 (a)`` → strips footnote markers
    - Rejected: ``12.5%`` in money context, ``3.1.2`` (note reference)
    """
    if not text:
        return ParsedNumber(None)

    s = text.strip()

    # ── Dash / nil → zero ────────────────────────────────────────────────
    if s in ("—", "–", "-", "Nil", "NIL", "nil", "", "na", "NA", "n.a.", "N.A."):
        return ParsedNumber(Decimal("0"), dash_as_zero=True)

    # ── Strip currency prefix ────────────────────────────────────────────
    s = _strip_currency(s)

    # ── Strip footnote markers (*, ¹, (a), etc.) ────────────────────────
    s = _strip_footnotes(s)

    # ── Rejected patterns ────────────────────────────────────────────────
    if "%" in s:
        return ParsedNumber(None)       # percentage, not a money value
    if s.count(".") >= 2:
        return ParsedNumber(None)       # looks like a note reference (3.1.2)

    # ── Detect sign (parentheses → negative) ─────────────────────────────
    negative = False
    original = s
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # ── Strip leading minus ──────────────────────────────────────────────
    if s.startswith("-"):
        negative = not negative
        s = s[1:].strip()

    # ── Remove commas and spaces (Indian grouping uses commas freely) ────
    s = s.replace(",", "").replace(" ", "").replace("\u00a0", "").replace("\u2009", "")

    # ── Parse ────────────────────────────────────────────────────────────
    if not s:
        return ParsedNumber(None)

    try:
        value = Decimal(s)
    except InvalidOperation:
        return ParsedNumber(None)

    if negative:
        value = -value

    # Sanity: reject values that look like dates (all digits, < 1000, 4-8 digits)
    if value == int(value) and 1900 <= value <= 2100 and "." not in original:
        # Could be a year — allow it (it might be legitimate)
        pass

    return ParsedNumber(value)


# ── Display formatting ───────────────────────────────────────────────────────

def format_inr(value: float | Decimal, unit: str = "crore", decimals: int = 2) -> str:
    """Format a number with Indian digit grouping for display.

    ``1234567.89`` → ``"12,34,567.89 Cr"`` (when unit="crore")
    """
    magnitude = UNIT_FACTORS.get(unit, 1)
    scaled = Decimal(str(value)) / Decimal(str(magnitude))

    # Format with Indian grouping
    sign = "-" if scaled < 0 else ""
    scaled = abs(scaled)

    integer_part = int(scaled)
    frac_part = f"{scaled - integer_part:.{decimals}f}".split(".")[1]

    # Indian grouping: last 3, then groups of 2
    int_str = str(integer_part)
    if len(int_str) <= 3:
        grouped = int_str
    else:
        last_three = int_str[-3:]
        rest = int_str[:-3]
        groups_of_2 = []
        while rest:
            groups_of_2.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(groups_of_2)) + "," + last_three

    unit_labels = {"crore": "Cr", "lakh": "L", "million": "M", "thousand": "K", "actual": ""}
    suffix = unit_labels.get(unit, "")
    label = f"₹ {sign}{grouped}.{frac_part}"
    if suffix:
        label += f" {suffix}"
    return label.strip()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_currency(s: str) -> str:
    """Remove ₹, Rs., INR prefix."""
    for prefix in ["\u20b9", "inr", "rs."]:
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def _strip_footnotes(s: str) -> str:
    """Remove trailing footnote markers like *, ¹, (a), etc. — NOT digits."""
    import re
    # Strip footnote superscripts and asterisks (but NOT digits)
    s = re.sub(r"[*\u00b9\u00b2\u00b3]+$", "", s)
    # Strip parenthetical letter markers like (a), (b), (1)
    s = re.sub(r"\s*\([a-z]\)\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()
