"""2D sensitivity matrix (growth × WACC)."""

from agent.models.valuation import DCFInputs, SensitivityResult
from agent.valuation.dcf import calculate_dcf, MIN_GORDON_SPREAD


def build_sensitivity_matrix(
    inputs: DCFInputs,
    wacc_range: tuple[float, float] = (0.08, 0.14),
    growth_range: tuple[float, float] = (0.01, 0.05),
    wacc_steps: int = 5,
    growth_steps: int = 5,
) -> SensitivityResult:
    """Generate 2D sensitivity: implied price for each (WACC, terminal growth)."""
    wacc_values = [wacc_range[0] + (wacc_range[1] - wacc_range[0]) * i / (wacc_steps - 1) for i in range(wacc_steps)]
    growth_values = [growth_range[0] + (growth_range[1] - growth_range[0]) * i / (growth_steps - 1) for i in range(growth_steps)]

    base_result = calculate_dcf(inputs)

    matrix: list[list[float]] = []
    for wacc in wacc_values:
        row: list[float] = []
        for g in growth_values:
            if g >= wacc - MIN_GORDON_SPREAD:
                row.append(0.0)
            else:
                res = calculate_dcf(inputs, wacc_override=wacc, tg_override=g)
                row.append(res.implied_price or 0.0)
        matrix.append(row)

    return SensitivityResult(
        ticker=inputs.ticker,
        wacc_values=wacc_values,
        growth_values=growth_values,
        implied_prices=matrix,
        base_wacc=base_result.wacc,
        base_growth=base_result.terminal_growth_rate,
        base_price=base_result.implied_price,
    )


def render_sensitivity_table(sensitivity: SensitivityResult) -> str:
    """Render the sensitivity matrix as formatted text."""
    headers = [f"WACC\\G" + ",".join(f"{g:.0%}" for g in sensitivity.growth_values)]
    lines = ["SENSITIVITY ANALYSIS: Implied Price per Share ($)", "=" * 60]

    for i, wacc in enumerate(sensitivity.wacc_values):
        row_prices = [f"${p:.0f}" for p in sensitivity.implied_prices[i]]
        lines.append(f"{wacc:.1%}   " + "  ".join(f"{p:>7}" for p in row_prices))

    lines.append("")
    lines.append(f"Base: WACC={sensitivity.base_wacc:.1%}, Growth={sensitivity.base_growth:.1%}, Price=${sensitivity.base_price:.0f}")

    return "\n".join(lines)
