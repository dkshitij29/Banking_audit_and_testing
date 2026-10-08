"""Per-market configuration for valuation inputs."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class MarketConfig(BaseModel):
    """Immutable market-level constants used by WACC / DCF / peers."""

    code: Literal["US", "IN"]
    currency: str
    risk_free_rate: float | None = None          # decimal, e.g. 0.073 → 7.3%
    equity_risk_premium: float | None = None      # decimal
    default_tax_rate: float
    beta_index: str                               # "^GSPC" | "^NSEI"
    terminal_growth_cap: float
    max_financials_age_days: int


# ── Defaults ──────────────────────────────────────────────────────────────────

_US: MarketConfig = MarketConfig(
    code="US",
    currency="USD",
    default_tax_rate=0.21,
    beta_index="^GSPC",
    terminal_growth_cap=0.03,
    max_financials_age_days=456,
)

_IN: MarketConfig = MarketConfig(
    code="IN",
    currency="INR",
    default_tax_rate=0.2517,
    beta_index="^NSEI",
    terminal_growth_cap=0.05,
    max_financials_age_days=456,
)


def get_market_config(code: str, risk_free_rate: float | None, equity_risk_premium: float | None) -> MarketConfig:
    """Return the config for *code*, injecting the env-sourced rates.

    If *code* is ``"IN"`` and either rate is ``None``, the returned config
    still has ``None`` — callers must check and raise ``ConfigError`` before
    using the config for valuation.
    """
    if code.upper() == "IN":
        return _IN.model_copy(update={
            "risk_free_rate": risk_free_rate,
            "equity_risk_premium": equity_risk_premium,
        })
    return _US.model_copy(update={
        "risk_free_rate": risk_free_rate,
        "equity_risk_premium": equity_risk_premium,
    })


def is_india_config_ready(risk_free_rate: float | None, equity_risk_premium: float | None) -> dict:
    """Return ``{"ready": True}`` or ``{"ready": False, "missing": [...]}``."""
    missing = []
    if risk_free_rate is None:
        missing.append("IN_RISK_FREE_RATE")
    if equity_risk_premium is None:
        missing.append("IN_EQUITY_RISK_PREMIUM")
    return {"ready": len(missing) == 0, "missing": missing}
