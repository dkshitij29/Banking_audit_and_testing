from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from enum import Enum


class Verdict(str, Enum):
    OVERVALUED = "Overvalued"
    FAIRLY_VALUED = "Fairly Valued"
    UNDERVALUED = "Undervalued"


class Rating(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class ResearchReport(BaseModel):
    company: str
    ticker: str
    current_price: float
    report_date: date
    verdict: Verdict
    fair_value_low: float
    fair_value_high: float
    fair_value_mid: float
    upside_pct: float
    rating: Rating
    confidence: str  # High, Medium, Low
    why: list[str] = Field(default_factory=list)
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    dcf_range: Optional[str] = None
    comps_table: Optional[str] = None
    sensitivity_table: Optional[str] = None
    key_assumptions: dict = Field(default_factory=dict)
    what_would_change_view: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Company: {self.company} ({self.ticker}) | Price: ${self.current_price:.2f} | Date: {self.report_date}",
            f"Verdict: {self.verdict.value} (fair value range ${self.fair_value_low:.0f}–${self.fair_value_high:.0f}, midpoint ${self.fair_value_mid:.0f}, ~{self.upside_pct:.0f}% upside)",
            f"Derived rating: {self.rating.value} (model-generated, confidence: {self.confidence})",
            "",
            f"Why:",
        ]
        for bullet in self.why:
            lines.append(f"  • {bullet}")
        lines.append("")
        lines.append("Bull case:")
        for point in self.bull_case:
            lines.append(f"  • {point}")
        lines.append("")
        lines.append("Bear case:")
        for point in self.bear_case:
            lines.append(f"  • {point}")
        lines.append("")
        lines.append("Red flags:")
        for flag in self.red_flags:
            lines.append(f"  • {flag}")
        lines.append("")
        if self.dcf_range:
            lines.append("Valuation detail — DCF:")
            lines.append(f"{self.dcf_range}")
            lines.append("")
        if self.comps_table:
            lines.append("Valuation detail — Comps:")
            lines.append(f"{self.comps_table}")
            lines.append("")
        if self.sensitivity_table:
            lines.append("Sensitivity (Growth × WACC):")
            lines.append(f"{self.sensitivity_table}")
            lines.append("")
        lines.append("Key assumptions:")
        for k, v in self.key_assumptions.items():
            lines.append(f"  • {k}: {v}")
        lines.append("")
        lines.append("What would change this view:")
        for item in self.what_would_change_view:
            lines.append(f"  • {item}")
        lines.append("")
        lines.append("Sources:")
        for source in self.sources:
            lines.append(f"  • {source}")
        lines.append("")
        lines.append("Disclaimer: Research support, not financial advice")
        return "\n".join(lines)
