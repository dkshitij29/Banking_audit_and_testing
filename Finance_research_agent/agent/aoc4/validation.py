"""Validation checks V1–V12 for extracted PeriodStatements.

Each check returns ``ValidationIssue`` objects. ERROR blocks valuation.
"""

from __future__ import annotations

from decimal import Decimal

from agent.aoc4.models import (
    Basis, Framework, Item, PeriodStatements, Source,
    ValidationIssue, IssueSeverity,
)


def run_validation(periods: list[PeriodStatements], *, source: Source | None = None) -> list[ValidationIssue]:
    """Run all applicable checks and return issues."""
    issues: list[ValidationIssue] = []
    if not periods:
        return issues

    src = source or periods[0].source

    for period in periods:
        # V1: Balance sheet balances
        issues.extend(_v1_balance_check(period))

        # V2a: revenue + other_income ≈ total_income
        issues.extend(_v2a_income_check(period, src))

        # V2b: total_income - total_expenses ≈ profit_before_tax
        issues.extend(_v2b_pbt_check(period, src))

        # V2c: profit_before_tax - tax ≈ profit_after_tax
        issues.extend(_v2c_pat_check(period, src))

        # V3: Cash flow cash ≈ BS cash
        issues.extend(_v3_cash_check(period, src))

        # V6: Magnitude sanity
        issues.extend(_v6_sanity(period))

        # V7: Period length
        issues.extend(_v7_period_length(period))

        # V12: Unmapped row ratio (placeholder — set by pdf_statements)
        # Would need the parser to pass unmapped count

    # V4: All periods share one basis
    issues.extend(_v4_basis_consistency(periods))

    # V8: History depth
    issues.extend(_v8_history_depth(periods))

    # V11: Staleness
    issues.extend(_v11_staleness(periods))

    return issues


def _tolerance(value: float, scale: str = "crore") -> float:
    """Tolerance = max(2 units at declared scale, 0.1% of the larger operand)."""
    from agent.aoc4.units import UNIT_FACTORS
    factor = UNIT_FACTORS.get(scale, 1)
    return max(2 * factor, abs(value) * 0.001)


def _items(p: PeriodStatements, *codes: Item):
    """Get values for item codes from a period."""
    return [p.items.get(c) for c in codes]


def _v1_balance_check(p: PeriodStatements) -> list[ValidationIssue]:
    """total_assets == total_equity_and_liabilities."""
    assets, eq_liab = _items(p, Item.TOTAL_ASSETS, Item.TOTAL_EQUITY_AND_LIABILITIES)
    if assets is None or eq_liab is None:
        return []
    diff = abs(assets - eq_liab)
    tol = max(Decimal("2"), abs(assets) * Decimal("0.001"))
    if diff > tol:
        return [ValidationIssue(
            code="V1_BALANCE_SHEET_DOES_NOT_BALANCE",
            severity=IssueSeverity.ERROR,
            message=f"Assets ({assets}) ≠ Equity+Liabilities ({eq_liab}), diff={diff}",
            period_end=p.period_end,
        )]
    return []


def _v2a_income_check(p: PeriodStatements, src: Source) -> list[ValidationIssue]:
    """revenue + other_income ≈ total_income."""
    rev, other, total = _items(p, Item.REVENUE_FROM_OPERATIONS, Item.OTHER_INCOME, Item.TOTAL_INCOME)
    if rev is None or total is None:
        return []
    computed = rev + (other or Decimal("0"))
    diff = abs(computed - total)
    tol = max(Decimal("2"), abs(total) * Decimal("0.001"))
    if diff > tol:
        sev = IssueSeverity.ERROR if src == Source.PDF_OCR else IssueSeverity.WARN
        return [ValidationIssue(
            code="V2A_INCOME_MISMATCH",
            severity=sev,
            message=f"Revenue+Other ({computed:.2f}) ≠ Total Income ({total:.2f})",
            period_end=p.period_end,
        )]
    return []


def _v2b_pbt_check(p: PeriodStatements, src: Source) -> list[ValidationIssue]:
    """total_income - total_expenses ≈ profit_before_tax."""
    total, expenses, pbt, exceptional = _items(
        p, Item.TOTAL_INCOME, Item.TOTAL_EXPENSES,
        Item.PROFIT_BEFORE_TAX, Item.EXCEPTIONAL_ITEMS,
    )
    if total is None or pbt is None:
        return []
    computed = total - (expenses or Decimal("0")) - (exceptional or Decimal("0"))
    diff = abs(computed - pbt)
    tol = max(Decimal("2"), abs(pbt) * Decimal("0.001"))
    if diff > tol:
        sev = IssueSeverity.ERROR if src == Source.PDF_OCR else IssueSeverity.WARN
        return [ValidationIssue(
            code="V2B_PBT_MISMATCH",
            severity=sev,
            message=f"Computed PBT ({computed:.2f}) ≠ Reported ({pbt:.2f})",
            period_end=p.period_end,
        )]
    return []


def _v2c_pat_check(p: PeriodStatements, src: Source) -> list[ValidationIssue]:
    """profit_before_tax - tax ≈ profit_after_tax."""
    pbt, tax, pat = _items(p, Item.PROFIT_BEFORE_TAX, Item.TAX_EXPENSE, Item.PROFIT_AFTER_TAX)
    if pbt is None or pat is None:
        return []
    computed = pbt - (tax or Decimal("0"))
    diff = abs(computed - pat)
    tol = max(Decimal("2"), abs(pat) * Decimal("0.001"))
    if diff > tol:
        sev = IssueSeverity.ERROR if src == Source.PDF_OCR else IssueSeverity.WARN
        return [ValidationIssue(
            code="V2C_PAT_MISMATCH",
            severity=sev,
            message=f"PBT-Tax ({computed:.2f}) ≠ PAT ({pat:.2f})",
            period_end=p.period_end,
        )]
    return []


def _v3_cash_check(p: PeriodStatements, src: Source) -> list[ValidationIssue]:
    """closing_cash_per_cfs ≈ cash_and_equivalents."""
    cfs_cash, bs_cash = _items(p, Item.CLOSING_CASH_PER_CFS, Item.CASH_AND_EQUIVALENTS)
    if cfs_cash is None or bs_cash is None:
        return []
    diff = abs(cfs_cash - bs_cash)
    tol = max(Decimal("2"), abs(bs_cash) * Decimal("0.001"))
    if diff > tol:
        sev = IssueSeverity.ERROR if src == Source.PDF_OCR else IssueSeverity.WARN
        return [ValidationIssue(
            code="V3_CASH_MISMATCH",
            severity=sev,
            message=f"CFS cash ({cfs_cash:.2f}) ≠ BS cash ({bs_cash:.2f})",
            period_end=p.period_end,
        )]
    return []


def _v4_basis_consistency(periods: list[PeriodStatements]) -> list[ValidationIssue]:
    """All periods must share one basis."""
    bases = {p.basis for p in periods if p.basis != Basis.UNKNOWN}
    if len(bases) > 1:
        return [ValidationIssue(
            code="V4_MIXED_BASIS",
            severity=IssueSeverity.ERROR,
            message=f"Periods have mixed basis: {bases}",
        )]
    return []


def _v6_sanity(p: PeriodStatements) -> list[ValidationIssue]:
    """Magnitude checks."""
    issues = []
    rev = p.items.get(Item.REVENUE_FROM_OPERATIONS) or 0
    assets = p.items.get(Item.TOTAL_ASSETS) or 0
    eq_cap = p.items.get(Item.EQUITY_SHARE_CAPITAL)

    if rev and assets and assets > 0:
        ratio = rev / assets
        if ratio < 0.01 or ratio > 50:
            issues.append(ValidationIssue(
                code="V6_UNUSUAL_REV_ASSET_RATIO",
                severity=IssueSeverity.WARN,
                message=f"Revenue/Assets = {ratio:.2f} (expected 0.01–50)",
                period_end=p.period_end,
            ))

    if eq_cap is not None and eq_cap <= 0:
        issues.append(ValidationIssue(
            code="V6_ZERO_SHARE_CAPITAL",
            severity=IssueSeverity.WARN,
            message="Equity share capital ≤ 0",
            period_end=p.period_end,
        ))

    return issues


def _v7_period_length(p: PeriodStatements) -> list[ValidationIssue]:
    """Period should be 12 ± 0.5 months."""
    if p.months < 11 or p.months > 13:
        return [ValidationIssue(
            code="V7_NON_STANDARD_PERIOD",
            severity=IssueSeverity.WARN,
            message=f"Period length = {p.months} months (expected 12)",
            period_end=p.period_end,
        )]
    return []


def _v8_history_depth(periods: list[PeriodStatements]) -> list[ValidationIssue]:
    """≥ 3 periods for DCF."""
    if len(periods) < 3:
        return [ValidationIssue(
            code="V8_INSUFFICIENT_HISTORY",
            severity=IssueSeverity.WARN,
            message=f"Only {len(periods)} period(s) available (need ≥ 3 for DCF)",
        )]
    return []


def _v11_staleness(periods: list[PeriodStatements]) -> list[ValidationIssue]:
    """Staleness check."""
    from datetime import date, timedelta
    latest = max(p.period_end for p in periods)
    days = (date.today() - latest).days
    if days > 456:
        return [ValidationIssue(
            code="V11_STALE",
            severity=IssueSeverity.WARN,
            message=f"Latest data is {days} days old (>{456} day threshold)",
            period_end=latest,
        )]
    return []
