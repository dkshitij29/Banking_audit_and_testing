"""CAPM-based Weighted Average Cost of Capital."""


def calculate_wacc(
    risk_free_rate: float = 0.043,
    beta: float = 1.0,
    equity_risk_premium: float = 0.0423,
    cost_of_debt: float = 0.05,
    tax_rate: float = 0.21,
    debt_ratio: float = 0.3,
) -> tuple[float, float]:
    """Compute WACC using CAPM.

    Returns:
        (cost_of_equity, wacc)
    """
    beta_adj = adjust_beta_blume(beta)
    cost_of_equity = risk_free_rate + beta_adj * equity_risk_premium
    equity_ratio = 1.0 - debt_ratio
    wacc = equity_ratio * cost_of_equity + debt_ratio * cost_of_debt * (1 - tax_rate)
    return cost_of_equity, wacc


def adjust_beta_blume(raw_beta: float) -> float:
    """ASYMMETRIC Blume adjustment: only for beta > 1.0.

    High-betta mean-reverts towards 1.0.
    Low-beta defensives kept raw.
    """
    if raw_beta > 1.0:
        return 2 / 3 * raw_beta + 1 / 3 * 1.0
    return raw_beta


def estimate_debt_ratio(
    total_debt: float,
    equity: float,
) -> float:
    """Estimate target debt ratio from balance sheet."""
    total_capital = total_debt + equity
    if total_capital <= 0:
        return 0.3
    return total_debt / total_capital


def estimate_tax_rate(
    income_tax_expense: float,
    pretax_income: float,
) -> float:
    """Estimate effective tax rate."""
    if not pretax_income or pretax_income == 0:
        return 0.21
    return max(0.0, min(0.4, income_tax_expense / pretax_income))
