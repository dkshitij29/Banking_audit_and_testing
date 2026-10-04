from pydantic import BaseModel, Field
from typing import Optional
from dataclasses import dataclass, field


class DCFInputs(BaseModel):
    ticker: str
    shares_outstanding: float
    tax_rate: float
    risk_free_rate: float = 0.043
    beta: float = 1.0
    equity_risk_premium: float = 0.0423
    cost_of_debt: float = 0.05
    debt_ratio: float = 0.3
    terminal_growth_rate: float = 0.03
    revenue_history: list[float] = Field(default_factory=list)
    ebitda_history: list[float] = Field(default_factory=list)
    fcf_history: list[float] = Field(default_factory=list)
    ebitda_margin: Optional[float] = None
    capex_pct_revenue: Optional[float] = None
    da_pct_revenue: Optional[float] = None
    nwc_pct_revenue: Optional[float] = None
    forward_growth: Optional[list[float]] = None
    net_debt: float = 0.0
    short_term_debt: float = 0.0
    long_term_debt: float = 0.0
    cash_and_equivalents: float = 0.0


class DCFResult(BaseModel):
    ticker: str
    implied_price: float
    enterprise_value: float
    equity_value: float
    pv_fcfs: float
    terminal_value: float
    pv_terminal_value: float
    wacc: float
    terminal_growth_rate: float
    projection_years: int = 10
    assumptions: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CompsData(BaseModel):
    ticker: str
    peers: list["PeerMetric"] = Field(default_factory=list)
    median_ev_ebitda: Optional[float] = None
    median_pe: Optional[float] = None
    median_pb: Optional[float] = None
    implied_price_ev_ebitda: Optional[float] = None
    implied_price_pe: Optional[float] = None
    implied_price_pb: Optional[float] = None
    implied_median_price: Optional[float] = None


class PeerMetric(BaseModel):
    ticker: str
    name: Optional[str] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    ev_ebitda: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ebitda: Optional[float] = None
    eps: Optional[float] = None
    share_price: Optional[float] = None
    book_value: Optional[float] = None


class SensitivityResult(BaseModel):
    ticker: str
    wacc_values: list[float]
    growth_values: list[float]
    implied_prices: list[list[float]]
    base_wacc: float
    base_growth: float
    base_price: float
