"""Weighted combination of DCF + comps → fair value range."""

from agent.models.valuation import DCFResult, CompsData


def combine_valuations(
    dcf: DCFResult,
    comps: CompsData,
    dcf_weight: float = 0.6,
    comps_weight: float = 0.4,
) -> dict:
    """Combine DCF and comps into a fair value range.

    Returns dict with:
    - fair_value_mid: weighted midpoint
    - fair_value_low: conservative bound
    - fair_value_high: optimistic bound
    - confidence: High/Medium/L based on agreement between methods
    """
    dcf_price = dcf.implied_price or 0
    comps_price = comps.implied_median_price or comps.implied_price_ev_ebitda or 0

    if dcf_price <= 0 and comps_price <= 0:
        return {
            "fair_value_low": 0,
            "fair_value_high": 0,
            "fair_value_mid": 0,
            "confidence": "Low",
            "dcf_price": 0,
            "comps_price": 0,
        }

    valid_prices = []
    if dcf_price > 0:
        valid_prices.append(dcf_price * dcf_weight)
    if comps_price > 0:
        valid_prices.append(comps_price * comps_weight)

    total_weight = dcf_weight if dcf_price > 0 else 0
    total_weight += comps_weight if comps_price > 0 else 0
    if total_weight > 0:
        total_weight = 1.0

    fair_value_mid = sum(valid_prices) / total_weight if total_weight > 0 else 0

    all_prices = []
    if dcf_price > 0:
        all_prices.append(dcf_price)
    if comps_price > 0:
        all_prices.append(comps_price)

    if len(all_prices) >= 2:
        divergence = abs(dcf_price - comps_price) / max(dcf_price, comps_price)
        if divergence < 0.10:
            confidence = "High"
        elif divergence < 0.25:
            confidence = "Medium"
        else:
            confidence = "Low"
    else:
        confidence = "Low"

    lower_spread = 0.15
    upper_spread = 0.20

    fair_value_low = fair_value_mid * (1 - lower_spread)
    fair_value_high = fair_value_mid * (1 + upper_spread)

    return {
        "fair_value_low": max(0, fair_value_low),
        "fair_value_high": fair_value_high,
        "fair_value_mid": fair_value_mid,
        "confidence": confidence,
        "dcf_price": dcf_price,
        "comps_price": comps_price,
    }
