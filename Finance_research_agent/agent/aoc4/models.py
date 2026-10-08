"""AOC-4 / India extension — Pydantic data models.

All monetary values are absolute INR ``Decimal``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Document typing ──────────────────────────────────────────────────────────

class DocType(str, Enum):
    FORM = "form"
    FINANCIAL_STATEMENTS = "financial_statements"
    AUDITOR_REPORT = "auditor_report"
    BOARD_REPORT = "board_report"
    XBRL = "xbrl"
    ANNEXURE = "annexure"
    OTHER = "other"


class Basis(str, Enum):
    STANDALONE = "standalone"
    CONSOLIDATED = "consolidated"
    UNKNOWN = "unknown"


class Framework(str, Enum):
    IND_AS = "ind_as"
    INDIAN_GAAP = "indian_gaap"
    UNKNOWN = "unknown"


class Source(str, Enum):
    XBRL = "xbrl"
    PDF_TEXT = "pdf_text"
    PDF_OCR = "pdf_ocr"
    LLM_ASSISTED = "llm_assisted"


# ── Line-item enum ───────────────────────────────────────────────────────────

class Item(str, Enum):
    # Balance sheet
    TOTAL_ASSETS = "total_assets"
    TOTAL_EQUITY = "total_equity"
    TOTAL_EQUITY_AND_LIABILITIES = "total_equity_and_liabilities"
    EQUITY_SHARE_CAPITAL = "equity_share_capital"
    PREFERENCE_SHARE_CAPITAL = "preference_share_capital"
    OTHER_EQUITY = "other_equity"
    BORROWINGS_NON_CURRENT = "borrowings_non_current"
    BORROWINGS_CURRENT = "borrowings_current"
    CURRENT_MATURITIES_LTD = "current_maturities_ltd"
    LEASE_LIABILITIES_NON_CURRENT = "lease_liabilities_non_current"
    LEASE_LIABILITIES_CURRENT = "lease_liabilities_current"
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"
    OTHER_BANK_BALANCES = "other_bank_balances"
    CURRENT_INVESTMENTS = "current_investments"
    TRADE_RECEIVABLES = "trade_receivables"
    INVENTORIES = "inventories"
    TRADE_PAYABLES = "trade_payables"
    TOTAL_CURRENT_ASSETS = "total_current_assets"
    TOTAL_CURRENT_LIABILITIES = "total_current_liabilities"
    # P&L
    REVENUE_FROM_OPERATIONS = "revenue_from_operations"
    OTHER_INCOME = "other_income"
    TOTAL_INCOME = "total_income"
    TOTAL_EXPENSES = "total_expenses"
    FINANCE_COSTS = "finance_costs"
    DEPRECIATION_AMORTISATION = "depreciation_amortisation"
    EXCEPTIONAL_ITEMS = "exceptional_items"
    PROFIT_BEFORE_TAX = "profit_before_tax"
    CURRENT_TAX = "current_tax"
    DEFERRED_TAX = "deferred_tax"
    TAX_EXPENSE = "tax_expense"
    PROFIT_AFTER_TAX = "profit_after_tax"
    # Cash flow
    CASH_FROM_OPERATIONS = "cash_from_operations"
    CAPEX = "capex"
    CLOSING_CASH_PER_CFS = "closing_cash_per_cfs"
    DIVIDENDS_PAID = "dividends_paid"


# ── Provenance ───────────────────────────────────────────────────────────────

class Provenance(BaseModel):
    doc_id: str
    page: int | None = None
    label_as_found: str | None = None
    raw_value: str | None = None
    dash_as_zero: bool = False
    source: Source


# ── Period statements ────────────────────────────────────────────────────────

class PeriodStatements(BaseModel):
    """Extracted financials for one fiscal period."""

    period_start: date | None = None
    period_end: date
    months: int = 12
    basis: Basis = Basis.UNKNOWN
    framework: Framework = Framework.UNKNOWN
    source: Source = Source.PDF_TEXT
    scale_detected: Literal["actual", "thousand", "lakh", "million", "crore"] = "crore"
    scale_origin: Literal["statement_header", "xbrl_rounding", "user_override"] = "statement_header"
    items: dict[Item, Decimal | None] = Field(default_factory=dict)
    provenance: dict[Item, Provenance] = Field(default_factory=dict)
    shares_outstanding: Decimal | None = None
    face_value_per_share: Decimal | None = None
    filing_doc_ids: list[str] = Field(default_factory=list)
    superseded_by: str | None = None

    @property
    def label(self) -> str:
        if self.period_end.month == 3 and self.period_end.day == 31:
            return f"FY{self.period_end.year % 100:02d}"
        return f"YE {self.period_end.strftime('%b-%Y')}"


# ── Document info ────────────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    doc_type: DocType
    confidence: float = 0.0
    classification_evidence: list[str] = Field(default_factory=list)
    basis: Basis = Basis.UNKNOWN
    period_end: date | None = None
    pages: int | None = None
    scanned: bool = False
    user_override: bool = False
    # page-range support for combined PDFs
    page_start: int | None = None
    page_end: int | None = None


# ── Validation ───────────────────────────────────────────────────────────────

class IssueSeverity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


class ValidationIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    period_end: date | None = None
    detail: dict[str, str] = Field(default_factory=dict)


# ── Red flags ────────────────────────────────────────────────────────────────

class RedFlag(BaseModel):
    code: str
    severity: Literal["high", "medium", "low", "info"]
    title: str
    evidence_quote: str = ""          # ≤ 200 chars
    doc_id: str = ""
    page: int | None = None
    method: Literal["rule", "rule+classifier", "computed"] = "rule"
    needs_review: bool = False


# ── Valuation modes ──────────────────────────────────────────────────────────

class ValuationMode(str, Enum):
    MARKET_RELATIVE = "market_relative"
    INTRINSIC_RANGE = "intrinsic_range"
    INTRINSIC_VS_REFERENCE = "intrinsic_vs_reference"
    COMPS_ONLY = "comps_only"
    UNSUPPORTED_SECTOR = "unsupported_sector"
    DISTRESSED = "distressed"
    EXTRACTION_ONLY = "extraction_only"


# ── Entity ───────────────────────────────────────────────────────────────────

class EntityInfo(BaseModel):
    cin: str | None = None
    ticker: str | None = None
    name: str | None = None
    listed: Literal["listed", "unlisted", "unknown"] = "unknown"
    sector: str | None = None
    sector_source: Literal["user", "yfinance", "llm_closed_set", "nic_hint", "unknown"] = "unknown"
    framework: Framework = Framework.UNKNOWN
    basis: Basis = Basis.UNKNOWN


class EquityValueRange(BaseModel):
    low_inr: float = 0.0
    mid_inr: float = 0.0
    high_inr: float = 0.0
    per_share_low: float | None = None
    per_share_mid: float | None = None
    per_share_high: float | None = None
    per_share_reliable: bool = True
    dlom_applied: float | None = None


class DataQuality(BaseModel):
    score: Literal["high", "medium", "low"] = "medium"
    primary_source: Source = Source.PDF_TEXT
    periods_available: int = 0
    data_as_of: date | None = None
    staleness_days: int = 0
    notes: list[str] = Field(default_factory=list)


# ── Compact period summary (for API response) ────────────────────────────────

class PeriodSummary(BaseModel):
    label: str
    period_end: str       # ISO date string
    source: str
    basis: str | None = None
    framework: str | None = None
