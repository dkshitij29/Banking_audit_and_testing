"""API model schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    providers: dict


class StageResult(BaseModel):
    stage: str
    status: str  # "complete" | "partial" | "skipped"
    summary: str


class ValuationMetrics(BaseModel):
    dcf_implied_price: float | None = None
    comps_implied_price: float | None = None
    fair_value_low: float = 0
    fair_value_high: float = 0
    fair_value_mid: float = 0
    current_price: float = 0
    upside_pct: float = 0
    confidence: str = "Low"
    wacc: float | None = None
    terminal_growth: float | None = None


class AnalyzeResponse(BaseModel):
    verdict: str  # "UNDERVALUED" | "OVERVALUED" | "FAIRLY_VALUED"
    rating: str   # "BUY" | "HOLD" | "SELL"
    reasoning: str
    stages: list[StageResult] = Field(default_factory=list)
    valuation: ValuationMetrics = Field(default_factory=ValuationMetrics)
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    dcf_assumptions: dict = Field(default_factory=dict)
    what_would_change: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
