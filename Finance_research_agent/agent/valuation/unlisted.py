"""Unlisted company valuation helpers.

Computes unlevered beta from peers, relever, applies DLOM, estimates cost of debt.
"""

from __future__ import annotations

from agent.config.markets import MarketConfig


def unlever_beta(beta_l: float, debt_equity: float, tax_rate: float) -> float:
    """Unlever a listed beta: β_u = β_L / (1 + (1−t)·D/E)."""
    if debt_equity <= 0:
        return beta_l
    return beta_l / (1 + (1 - tax_rate) * debt_equity)


def relever_beta(beta_u: float, debt_equity: float, tax_rate: float) -> float:
    """Relever an unlevered beta at the target D/E: β_L = β_u × (1 + (1−t)·D/E)."""
    if debt_equity <= 0:
        return beta_u
    return beta_u * (1 + (1 - tax_rate) * debt_equity)


def median_unlevered_beta(
    peer_betas: list[float],
    peer_de_ratios: list[float],
    peer_tax_rates: list[float],
) -> float:
    """Compute median unlevered beta from peer set."""
    if not peer_betas:
        return 1.0

    unlevered = []
    for i, beta_l in enumerate(peer_betas):
        de = peer_de_ratios[i] if i < len(peer_de_ratios) else 0.3
        t = peer_tax_rates[i] if i < len(peer_tax_rates) else 0.25
        unlevered.append(unlever_beta(beta_l, de, t))

    unlevered.sort()
    mid = len(unlevered) // 2
    if len(unlevered) % 2 == 0 and len(unlevered) > 1:
        return (unlevered[mid - 1] + unlevered[mid]) / 2
    return unlevered[mid]


def estimate_cost_of_debt(
    finance_costs: float,
    average_borrowings: float,
    risk_free_rate: float,
    *,
    bounds: tuple[float, float] = (0.005, 0.12),
) -> float:
    """Effective cost of debt = finance_costs / average_borrowings.

    Bounded to [risk_free_rate + spread_low, risk_free_rate + spread_high].
    """
    if average_borrowings <= 0:
        return risk_free_rate + 0.03  # assume 3% spread

    rate = finance_costs / average_borrowings
    lower = risk_free_rate + bounds[0]
    upper = risk_free_rate + bounds[1]
    return max(lower, min(upper, rate))


def apply_dlom(equity_value: float, dlom: float = 0.20) -> float:
    """Apply discount for lack of marketability.

    *dlom* is a fraction: 0.20 = 20% discount.
    """
    if dlom < 0 or dlom > 1:
        raise ValueError(f"DLOM must be 0–1, got {dlom}")
    return equity_value * (1 - dlom)
