"""Financial-sector detection and routing.

Detects banks, NBFCs, insurers, etc. and routes to UNSUPPORTED_SECTOR
because FCFF DCF is not meaningful for financial firms.
"""

from __future__ import annotations


# Text signals that indicate a financial-sector entity
_FINANCIAL_SECTOR_SIGNALS = [
    "non-banking financial company",
    "nbf",
    "reserve bank of india act",
    "prudential norms",
    "insurance act",
    "banking regulation",
    "schedule iii division iii",
    "nbfc",
]

_FINANCIAL_SECTOR_LABELS = {
    "banks", "banking", "insurance", "financials", "financial services",
    "nbf", "nbfc", "housing finance", "broking", "asset management",
}


def is_financial_sector(
    sector: str | None = None,
    industry: str | None = None,
    description: str = "",
) -> bool:
    """Return True if the entity appears to be a financial-sector company.

    Checks sector/industry labels and text signals in the description.
    """
    if sector and sector.lower() in _FINANCIAL_SECTOR_LABELS:
        return True
    if industry and industry.lower() in _FINANCIAL_SECTOR_LABELS:
        return True

    desc_lower = description.lower()
    for signal in _FINANCIAL_SECTOR_SIGNALS:
        if signal in desc_lower:
            return True

    return False
