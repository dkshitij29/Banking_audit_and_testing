"""Discounted Cash Flow valuation (FCFF method)."""

from agent.models.valuation import DCFInputs, DCFResult
from agent.valuation.wacc import calculate_wacc, adjust_beta_blume


MIN_GORDON_SPREAD = 0.02  # Minimum spread between WACC and terminal growth


def calculate_dcf(inputs: DCFInputs, wacc_override: float = None, tg_override: float = None, mid_year: bool = False) -> DCFResult:
    """Full DCF: FCFF projection + terminal value + implied price.

    Steps:
    1. Compute WACC (or use override)
    2. Project revenue, EBITDA, FCFF year-by-year
    3. Discount each FCFF
    4. Terminal value via Gordon Growth
    5. Equity value = EV - net debt → implied price
    """
    warnings: list[str] = []
    projection_years = min(max(len(inputs.forward_growth) if inputs.forward_growth else 10, 5), 15)

    if wacc_override:
        wacc = wacc_override
        cost_of_equity = wacc
    else:
        cost_of_equity, wacc = calculate_wacc(
            risk_free_rate=inputs.risk_free_rate,
            beta=inputs.beta,
            equity_risk_premium=inputs.equity_risk_premium,
            cost_of_debt=inputs.cost_of_debt,
            tax_rate=inputs.tax_rate,
            debt_ratio=inputs.debt_ratio,
        )

    terminal_growth = tg_override or inputs.terminal_growth_rate

    if terminal_growth >= wacc:
        warnings.append(f"Terminal growth ({terminal_growth:.1%}) >= WACC ({wacc:.1%}). Reducing terminal growth.")
        terminal_growth = wacc - MIN_GORDON_SPREAD

    if wacc - terminal_growth < MIN_GORDON_SPREAD:
        warnings.append(f"WACC - terminal growth too narrow ({(wacc - terminal_growth):.1%}). Using minimum spread.")
        terminal_growth = wacc - MIN_GORDON_SPREAD

    latest_revenue = _get_latest(inputs.revenue_history)
    latest_ebitda = _get_latest(inputs.ebitda_history)

    if not latest_revenue or latest_revenue <= 0:
        return DCFResult(
            ticker=inputs.ticker,
            implied_price=0,
            enterprise_value=0,
            equity_value=0,
            pv_fcfs=0,
            terminal_value=0,
            pv_terminal_value=0,
            wacc=wacc,
            terminal_growth_rate=terminal_growth,
            projection_years=projection_years,
            warnings=["No valid revenue history to project from."],
        )

    ebitda_margin = inputs.ebitda_margin or (_normalize(latest_ebitda) / latest_revenue) if latest_ebitda else 0.2
    da_pct = inputs.da_pct_revenue or 0.05
    capex_pct = inputs.capex_pct_revenue or 0.06
    nwc_pct = inputs.nwc_pct_revenue or 0.05

    growth_schedule = inputs.forward_growth or _infer_growth_schedule(inputs.revenue_history, projection_years)

    pv_fcfs = 0.0
    projected_revenue = latest_revenue

    for year in range(1, projection_years + 1):
        g = growth_schedule[min(year - 1, len(growth_schedule) - 1)]
        projected_revenue *= (1 + g)

        ebitda_projected = projected_revenue * ebitda_margin
        da_projected = projected_revenue * da_pct
        ebit_projected = ebitda_projected - da_projected
        capex_projected = projected_revenue * capex_pct
        nwc_delta = projected_revenue * g * nwc_pct if g > 0 else 0

        fcf = ebit_projected * (1 - inputs.tax_rate) + da_projected - capex_projected - nwc_delta

        t = year - 0.5 if mid_year else year
        pv_fcfs += fcf / ((1 + wacc) ** t)

    terminal_revenue = projected_revenue * (1 + terminal_growth)
    terminal_fcf = _terminal_fcf(
        terminal_revenue, terminal_growth, ebitda_margin, da_pct, capex_pct,
        nwc_pct, inputs.tax_rate,
    )

    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** (projection_years - 0.5 if mid_year else projection_years))

    enterprise_value = pv_fcfs + pv_terminal
    net_debt = inputs.net_debt or (inputs.short_term_debt + inputs.long_term_debt - inputs.cash_and_equivalents)
    equity_value = enterprise_value - net_debt

    if equity_value <= 0:
        warnings.append(f"Equity value is negative (${equity_value/1e9:.1f}B). Implied price set to 0.")

    shares = inputs.shares_outstanding
    implied_price = max(0, equity_value / shares) if shares and shares > 0 else 0

    return DCFResult(
        ticker=inputs.ticker,
        implied_price=implied_price,
        enterprise_value=enterprise_value,
        equity_value=max(0, equity_value),
        pv_fcfs=pv_fcfs,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal,
        wacc=wacc,
        terminal_growth_rate=terminal_growth,
        projection_years=projection_years,
        assumptions={
            "risk_free_rate": inputs.risk_free_rate,
            "beta": adjust_beta_blume(inputs.beta),
            "equity_risk_premium": inputs.equity_risk_premium,
            "cost_of_debt": inputs.cost_of_debt,
            "tax_rate": inputs.tax_rate,
            "debt_ratio": inputs.debt_ratio,
            "ebitda_margin": ebitda_margin,
            "terminal_growth": terminal_growth,
        },
        warnings=warnings,
    )


def _terminal_fcf(
    terminal_revenue: float,
    terminal_growth: float,
    ebitda_margin: float,
    da_pct: float,
    capex_pct: float,
    nwc_pct: float,
    tax_rate: float,
) -> float:
    """Steady-state FCF for Gordon perpetuity.

    Normalizes capex to maintenance: use min(D&A%, CapEx%) as maintenance reinvestment.
    """
    anchor = min(da_pct, capex_pct)
    da = terminal_revenue * anchor
    ebit = terminal_revenue * ebitda_margin - da
    capex = da * (1 + terminal_growth)
    fcf = ebit * (1 - tax_rate) + da - capex - terminal_revenue * nwc_pct
    return fcf


def _get_latest(history: list[float]) -> float:
    if not history:
        return 0.0
    for v in reversed(history):
        if v and v > 0:
            return v
    return 0.0


def _normalize(value: float) -> float:
    return value if value else 0.0


def _infer_growth_schedule(revenue_history: list[float], years: int) -> list[float]:
    """Infer growth rate from historical revenue CAGR."""
    if len(revenue_history) < 2:
        return [0.05] * years

    valid = [r for r in revenue_history if r and r > 0]
    if len(valid) < 2:
        return [0.05] * years

    oldest = valid[-1]
    newest = valid[0]
    n = len(valid) - 1

    if oldest <= 0:
        return [0.05] * years

    cagr = (newest / oldest) ** (1 / n) - 1

    blended = []
    for i in range(years):
        decay = 1 - (i / (years + 1))
        g = cagr * (0.5 + 0.5 * decay)
        blended.append(max(-0.05, min(0.25, g)))

    return blended


def calculate_sensitivity(
    inputs: DCFInputs,
    wacc_range: tuple[float, float] = (0.08, 0.14),
    tg_range: tuple[float, float] = (0.01, 0.05),
    wacc_steps: int = 5,
    tg_steps: int = 5,
) -> dict:
    """2D sensitivity grid: implied price for each (WACC, terminal growth).

    Matrix is indexed [growth_row][wacc_col] to match frontend SensitivityTable.
    """
    wacc_values = [wacc_range[0] + (wacc_range[1] - wacc_range[0]) * i / (wacc_steps - 1) for i in range(wacc_steps)]
    tg_values = [tg_range[0] + (tg_range[1] - tg_range[0]) * i / (tg_steps - 1) for i in range(tg_steps)]

    matrix = []
    for g in tg_values:           # outer loop = growth rows
        row = []
        for w in wacc_values:     # inner loop = wacc columns
            if g >= w - MIN_GORDON_SPREAD:
                row.append(0.0)
            else:
                result = calculate_dcf(inputs, wacc_override=w, tg_override=g)
                row.append(result.implied_price or 0.0)
        matrix.append(row)

    base = calculate_dcf(inputs)

    return {
        "wacc_values": wacc_values,
        "growth_values": tg_values,
        "implied_prices": matrix,
        "base_wacc": base.wacc,
        "base_growth": base.terminal_growth_rate,
    }
