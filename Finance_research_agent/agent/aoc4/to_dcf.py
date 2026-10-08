"""Convert AOC-4 PeriodStatements → DCFInputs.

Handles India-specific mapping: Schedule III items → standard DCF fields.
"""

from __future__ import annotations

from decimal import Decimal

from agent.aoc4.models import Item, PeriodStatements, Basis, Framework, Source
from agent.models.valuation import DCFInputs


def periods_to_dcf_inputs(
    periods: list[PeriodStatements],
    *,
    ticker: str = "",
    shares_outstanding: float | None = None,
    risk_free_rate: float = 0.043,
    equity_risk_premium: float = 0.0423,
    beta: float | None = None,
    default_tax_rate: float = 0.2517,
    include_leases_in_debt: bool = True,
    include_other_bank_balances: bool = True,
    treat_current_investments_as_cash: bool = False,
) -> DCFInputs:
    """Map PeriodStatements to DCFInputs using the latest period.

    *periods* must be sorted ascending by period_end.
    """
    if not periods:
        raise ValueError("No periods to convert")

    latest = periods[-1]
    items = latest.items

    # ── Revenue history ──────────────────────────────────────────────────
    revenue_history = []
    ebitda_history = []
    for p in periods:
        rev = p.items.get(Item.REVENUE_FROM_OPERATIONS)
        if rev and rev > 0:
            revenue_history.append(float(rev))
        # EBITDA = PBT - Exceptional + Finance Costs + D&A - Other Income
        ebitda = _compute_ebitda(p.items)
        if ebitda and ebitda > 0:
            ebitda_history.append(float(ebitda))

    # Reverse so newest first (DCF expects newest-first)
    revenue_history.reverse()
    ebitda_history.reverse()

    # ── Debt ─────────────────────────────────────────────────────────────
    short_debt = float(items.get(Item.BORROWINGS_CURRENT) or 0)
    short_debt += float(items.get(Item.CURRENT_MATURITIES_LTD) or 0)

    long_debt = float(items.get(Item.BORROWINGS_NON_CURRENT) or 0)
    if include_leases_in_debt:
        long_debt += float(items.get(Item.LEASE_LIABILITIES_NON_CURRENT) or 0)
        short_debt += float(items.get(Item.LEASE_LIABILITIES_CURRENT) or 0)

    # ── Cash ─────────────────────────────────────────────────────────────
    cash = float(items.get(Item.CASH_AND_EQUIVALENTS) or 0)
    if include_other_bank_balances:
        cash += float(items.get(Item.OTHER_BANK_BALANCES) or 0)
    if treat_current_investments_as_cash:
        cash += float(items.get(Item.CURRENT_INVESTMENTS) or 0)

    net_debt = short_debt + long_debt - cash

    # ── Shares outstanding ───────────────────────────────────────────────
    if shares_outstanding is None:
        eq_cap = items.get(Item.EQUITY_SHARE_CAPITAL)
        face_value = latest.face_value_per_share
        if eq_cap and face_value and face_value > 0:
            shares_outstanding = float(eq_cap / face_value)
        else:
            shares_outstanding = 0

    # ── Debt ratio ──────────────────────────────────────────────────────
    total_debt = short_debt + long_debt
    total_equity = float(items.get(Item.TOTAL_EQUITY) or 0)
    debt_ratio = total_debt / (total_debt + total_equity) if (total_debt + total_equity) > 0 else 0.3

    # ── Tax rate ────────────────────────────────────────────────────────
    tax_rate = _estimate_effective_tax_rate(periods) or default_tax_rate

    # ── Beta ────────────────────────────────────────────────────────────
    if beta is None:
        beta = 1.0  # will be overridden by compute_beta() for listed

    # ── Build DCFInputs ─────────────────────────────────────────────────
    return DCFInputs(
        ticker=ticker or "AOC4",
        shares_outstanding=shares_outstanding,
        tax_rate=tax_rate,
        risk_free_rate=risk_free_rate,
        beta=beta,
        equity_risk_premium=equity_risk_premium,
        debt_ratio=debt_ratio,
        revenue_history=revenue_history,
        ebitda_history=ebitda_history,
        net_debt=net_debt,
        short_term_debt=short_debt,
        long_term_debt=long_debt,
        cash_and_equivalents=cash,
    )


def _compute_ebitda(items: dict[Item, Decimal | None]) -> Decimal:
    """EBITDA = PBT - Exceptional + Finance Costs + D&A - Other Income.

    Signs per Schedule III:
    - Exceptional gains are subtracted, losses added back
    - Finance costs are positive (expense), so added back
    """
    pbt = items.get(Item.PROFIT_BEFORE_TAX) or Decimal("0")
    exceptional = items.get(Item.EXCEPTIONAL_ITEMS) or Decimal("0")
    finance_costs = items.get(Item.FINANCE_COSTS) or Decimal("0")
    da = items.get(Item.DEPRECIATION_AMORTISATION) or Decimal("0")
    other_income = items.get(Item.OTHER_INCOME) or Decimal("0")

    return pbt - exceptional + finance_costs + da - other_income


def _estimate_effective_tax_rate(
    periods: list[PeriodStatements],
    *,
    min_periods: int = 1,
    bounds: tuple[float, float] = (0.10, 0.40),
) -> float | None:
    """Average effective tax rate across profitable periods.

    Returns None if no valid periods.
    """
    rates = []
    for p in periods:
        pbt = p.items.get(Item.PROFIT_BEFORE_TAX)
        tax = p.items.get(Item.TAX_EXPENSE)
        if pbt and pbt > 0 and tax:
            rate = float(tax / pbt)
            if bounds[0] <= rate <= bounds[1]:
                rates.append(rate)

    if len(rates) >= min_periods:
        return sum(rates) / len(rates)
    return None
