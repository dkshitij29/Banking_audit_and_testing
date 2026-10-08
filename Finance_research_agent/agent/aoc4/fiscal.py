"""Fiscal period parsing, FY labels, period-length checks."""

from __future__ import annotations

from datetime import date, timedelta
import re


# Recognised date formats in Indian filings
_DATE_PATTERNS = [
    # "31 March 2025"
    re.compile(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})"),
    # "March 31, 2025"
    re.compile(r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})"),
    # "31.03.2025" / "31/03/2025"
    re.compile(r"(\d{2})[./-](\d{2})[./-](\d{4})"),
]

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse_date(text: str) -> date | None:
    """Try each pattern and return the first ``date`` match."""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups) == 3 and groups[1].lower() in _MONTH_MAP:
                # "31 March 2025"
                day, month_str, year = int(groups[0]), _MONTH_MAP[groups[1].lower()], int(groups[2])
                return date(year, month_str, day)
            elif len(groups) == 3 and groups[0].lower() in _MONTH_MAP:
                # "March 31, 2025"
                month_str, day, year = _MONTH_MAP[groups[0].lower()], int(groups[1]), int(groups[2])
                return date(year, month_str, day)
            elif len(groups) == 3:
                # DD.MM.YYYY
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                return date(year, month, day)
        except (ValueError, TypeError):
            continue
    return None


def months_between(start: date, end: date) -> int:
    """Approximate months between two dates (handles year boundary)."""
    if start is None:
        return 12
    delta = (end - start).days
    return max(1, round(delta / 30.44))


def is_standard_period(start: date | None, end: date, tolerance_days: int = 15) -> bool:
    """Check if period is ~12 months (± tolerance)."""
    if start is None:
        return True  # can't check
    delta = (end - start).days
    return abs(delta - 365) <= tolerance_days


def period_label(period_end: date, months: int = 12) -> str:
    """``FY25`` when March 31; otherwise ``YE Mar-2025``."""
    if period_end.month == 3 and period_end.day == 31 and months == 12:
        return f"FY{period_end.year % 100:02d}"
    return f"YE {period_end.strftime('%b-%Y')}"
