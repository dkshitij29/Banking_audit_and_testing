# AOC-4 / India Extension: Implementation Spec

**Target system:** Finance Research Agent (`Finance_research_agent/`)
**Audience:** the coding agent implementing this change
**Status:** draft v1
**Companion to:** "2. Finance Research Agent" spec (5-stage pipeline, PydanticAI, yfinance, BM25, deterministic valuation)

> File paths and class names below are taken from the existing spec. Verify every one against the real code before editing. Where this document and the code disagree, the code wins, and you record the difference in `docs/aoc4_findings.md`.

---

## 0. How to use this document

1. **Read before writing.** Before any change, read these and write a one-page summary of how they behave in `docs/aoc4_findings.md`:
   `agent/pipeline/research.py`, `agent/api/server.py`, `agent/models/api.py`, `agent/valuation/{wacc,dcf,multiples,peer_screen,sensitivity,synthesis}.py`, `agent/agents/{analysis,debate}.py`, `agent/sec/qa.py`, the `parse_filing()` implementation, `MarketDataProvider`, `Settings`, `ResearchDeps`, and `frontend/src/App.jsx`.
   Pay particular attention to: the ordering convention of `revenue_history` / `ebitda_history` (oldest-first or newest-first), the type of `red_flags` in `AnalyzeResponse`, and how `find_peers()` gets its universe.
2. **Do not break the US path.** Run the existing tests before starting and after every phase. All new behaviour sits behind `market="IN"` or the new `/api/aoc4/*` endpoints. The existing `/api/analyze` contract does not change.
3. **Invariant: numbers by code, the LLM narrates.** No LLM output may feed a number into valuation. The only permitted LLM roles are (a) narration, (b) closed-set classification (labels from a fixed list, validated after the fact), and (c) optional, flagged, off-by-default extraction fallback (§8.5).
4. **Never guess external facts.** Anything listed in §16 (XBRL concept names, unit scaling in instances, bundle file naming) must be established by inspecting real sample files. Write a discovery script, run it, record the result, then code against the result.
5. **Fail loudly.** A wrong number that looks plausible is the worst outcome of this feature. Prefer an explicit error or an `INCONCLUSIVE` verdict over a silent best guess.
6. Work phase by phase (§15). Each phase must be mergeable on its own and meet its Definition of Done.
7. Record non-obvious decisions in `docs/decisions.md` (date, decision, reason).

---

## 1. Goals and non-goals

### Goals
- G1. Accept an **AOC-4 bundle** (multiple files or a zip) for an Indian company, listed or unlisted, and extract structured financial statements for one or more fiscal years.
- G2. Prefer **XBRL** when present; fall back to **PDF text extraction**, then **OCR**, with validation at every step.
- G3. Run the existing valuation machinery with **India-appropriate inputs** (INR, Indian tax rate, India risk-free rate, Nifty-based beta).
- G4. Support **unlisted companies**: there is no market price, so produce an equity-value range and, by default, no Buy/Sell verdict.
- G5. Extract **India-specific red flags** (auditor opinion modifications, CARO findings, going-concern language, auditor changes, negative net worth, and similar).
- G6. Handle **Indian formats** correctly: lakh/crore units, `1,23,456.78` digit grouping, April–March fiscal years, Schedule III line items, Ind AS vs Indian GAAP.
- G7. Add Indian listed-company ticker support (`.NS` / `.BO`) as the foundation (Phase 0), since the listed path and the peer universe depend on it.

### Non-goals (this spec)
- Scraping the MCA portal or automating MCA purchases. Documents are uploaded by the user.
- Banks, NBFCs, insurers, and other financial-sector valuation. Detect and route; do not value. (Optional later: §15 Phase 6.)
- TTM / quarterly updating from exchange filings, earnings-call transcripts, Monte Carlo, LBO, SOTP.
- Persistent storage of uploaded filings. The service stays stateless.
- LLPs (they file Form 8 / Form 11, not AOC-4).

---

## 2. Domain primer: what AOC-4 is

This section is context for the coding agent. Do not hard-code any "fact" below that §16 marks as needing verification.

- **Form AOC-4** is the e-form Indian companies file with the Registrar of Companies (ROC) at the Ministry of Corporate Affairs (MCA) to submit their **financial statements** (Companies Act, 2013, Section 137). It is due within 30 days of the AGM. **AOC-4 CFS** is the variant for **consolidated** statements.
- Variants seen in practice: AOC-4 (XBRL), AOC-4 (non-XBRL), AOC-4 CFS. XBRL is required for certain classes of companies (thresholds on listing status, paid-up capital, turnover, and Ind AS applicability; they have changed over time, so do not hard-code them). Smaller companies file non-XBRL, which means **PDF is likely the main path for unlisted companies**.
- A downloaded public document set typically contains some of:
  - the form itself (mostly metadata)
  - **financial statements**: balance sheet, statement of profit and loss, cash flow statement, statement of changes in equity, notes
  - **independent auditor's report**, with the **CARO** annexure (Companies (Auditor's Report) Order, 2020)
  - **Board's Report** (also called Directors' Report) and its annexures (for example Form AOC-2 for related-party contracts, Form AOC-1 for subsidiaries, CSR report, secretarial audit Form MR-3)
  - an **XBRL instance document** (`.xml` / `.xbrl`), for XBRL filers
- **Accounting frameworks:** **Ind AS** (converged with IFRS; Schedule III *Division II*) or **Indian GAAP / AS** (Schedule III *Division I*). NBFCs following Ind AS use *Division III*. Line-item names differ between divisions.
- **Fiscal year:** usually 1 April to 31 March. "FY25" means the year ending 31 March 2025. Some companies use other year-ends. Always derive from the period-end date in the document.
- **Units:** statements are stated in actual rupees, thousands, lakhs (1 lakh = 100,000), millions, or crores (1 crore = 10,000,000). The unit is stated in a header line, and varies between companies.
- **Standalone vs consolidated:** never mix them in one analysis.
- **Public access:** these documents are public records, obtained manually from MCA's "View Public Documents" service (fee per document) or through a licensed data provider. The system never fetches from MCA itself.
- **Staleness:** an AOC-4 reflects a year-end typically 6–15 months old at the time of analysis. Always surface the period-end date and the staleness to the user.

---

## 3. Design principles and invariants

| # | Principle | Consequence |
|---|-----------|-------------|
| P1 | Numbers by code | All figures come from XBRL facts or deterministic table parsing, validated by accounting identities. |
| P2 | XBRL first, PDF second, OCR third | Record the `source` per period and per line item. Lower confidence as source quality drops. |
| P3 | Internal money is absolute INR | Convert from lakh/crore at the parse boundary. Convert back only for display. Use `Decimal` while parsing, `float` at the `DCFInputs` boundary. |
| P4 | No price, no verdict (by default) | Unlisted companies get an equity-value range and `NOT_APPLICABLE`. A verdict needs a user-supplied reference price or valuation. |
| P5 | Additive and flag-gated | US behaviour unchanged. New fields on shared models are optional with defaults. |
| P6 | Every extracted number is traceable | Keep provenance (document, page, label as found, XBRL concept) for each canonical line item. |
| P7 | Untrusted input | Uploaded documents are untrusted: zip-slip protection, size limits, no execution, prompt-injection-safe LLM prompts. |

---

## 4. Architecture

### 4.1 Scenario matrix

| Scenario | Entity | Price source | Financials source | `valuation_mode` | Verdict |
|----------|--------|--------------|-------------------|------------------|---------|
| A. US (existing) | listed US | yfinance | yfinance + SEC filing | `MARKET_RELATIVE` | unchanged |
| B. India listed, ticker only | listed | yfinance (`.NS`/`.BO`) | yfinance, validated | `MARKET_RELATIVE` | UNDERVALUED / OVERVALUED / FAIRLY_VALUED / INCONCLUSIVE |
| C. India listed + AOC-4 bundle | listed | yfinance | AOC-4 (XBRL > PDF), cross-checked vs yfinance | `MARKET_RELATIVE` | as B |
| D. India unlisted + AOC-4 bundle | unlisted | none | AOC-4 | `INTRINSIC_RANGE` | NOT_APPLICABLE |
| E. Unlisted + user reference price/valuation | unlisted | user-supplied | AOC-4 | `INTRINSIC_VS_REFERENCE` | verdict allowed, confidence capped at Medium |
| F. Financial-sector entity | any | n/a | n/a | `UNSUPPORTED_SECTOR` | INCONCLUSIVE |
| G. Going-concern doubt / adverse or disclaimed opinion | any | n/a | n/a | `DISTRESSED` | INCONCLUSIVE |

### 4.2 Pipeline for `/api/aoc4/analyze`

```
Stage 0 — BUNDLE      unzip safely → classify files → group by fiscal period
Stage 1 — INGEST      listed: yfinance (IN config) | unlisted: skipped (no price/beta)
Stage 2 — PARSE       XBRL facts → statements; else PDF tables; else OCR → PeriodStatements[]
                      sections → FilingSection[] → BM25Retriever index
Stage 3 — VALIDATE    accounting identities, units, basis, period length, history depth
Stage 4 — ANALYSE     red-flag rules + analysis agent (India prompt) + FilingQAIgent
Stage 5 — MODEL       route by valuation_mode: DCF / comps / sensitivity (pure Python)
Stage 6 — SYNTHESIZE  bull / bear / judge (mode-aware) → verdict via derive_verdict_in()
```

The `stages` array in the response keeps the existing shape. `0. BUNDLE` and `3. VALIDATE` are new entries. Confirm the frontend renders stage lists generically (§12).

---

## 5. Phase 0: India market foundation (prerequisite)

Needed by scenarios B and C, and for the peer universe used by D and E.

### 5.1 Per-market configuration

New file `agent/config/markets.py`:

```python
from pydantic import BaseModel
from typing import Literal

class MarketConfig(BaseModel):
    code: Literal["US", "IN"]
    currency: str                      # "USD" | "INR"
    risk_free_rate: float | None       # REQUIRED for DCF; None => DCF refuses to run
    equity_risk_premium: float | None  # REQUIRED for DCF
    default_tax_rate: float
    beta_index: str                    # "^GSPC" | "^NSEI"
    terminal_growth_cap: float
    max_financials_age_days: int

def get_market_config(code: str, settings: Settings) -> MarketConfig: ...
```

Environment variables (loaded through `Settings`):

```
IN_RISK_FREE_RATE=            # India 10-year G-sec yield as a decimal. REQUIRED. No default.
IN_EQUITY_RISK_PREMIUM=       # decimal. REQUIRED. No default.
IN_DEFAULT_TAX_RATE=0.2517    # statutory rate under the concessional regime incl. surcharge and cess; review per company
IN_TERMINAL_GROWTH_CAP=0.05
IN_MAX_FINANCIALS_AGE_DAYS=456
```

Rule: **if `risk_free_rate` or `equity_risk_premium` is `None`, any code path needing WACC raises `ConfigError("IN_RISK_FREE_RATE not set")`** and the API returns HTTP 503 with that message. Do not ship placeholder market numbers in code, because they go stale silently. `/api/health` reports `india_config_ready: bool` and which keys are missing.

Terminal growth guard: `g_terminal = min(cfg.terminal_growth_cap, risk_free_rate)` and require `WACC - g_terminal >= 0.02`, otherwise raise `ValuationError`.

### 5.2 Ticker resolver

New `agent/data/in_symbols.py`.
- Load the NSE equity list and BSE scrip master from CSV files committed under `data/` (with a `snapshot_date` column; the user refreshes them manually).
- `resolve_indian_symbol(raw: str) -> ResolvedSymbol(yf_ticker, exchange, name, isin|None)`:
  1. Already ends in `.NS` / `.BO` → validate and return.
  2. Exact match on NSE symbol → `SYMBOL.NS`.
  3. Numeric BSE code → `CODE.BO`.
  4. Fuzzy match on company name (rapidfuzz; threshold configurable). If more than one candidate scores close, return `AmbiguousSymbol(candidates)` and let the API return 422 with candidates. Never auto-pick on a near-tie.
- Symbols containing `&` or `-` are kept verbatim (`M&M.NS`, `BAJAJ-AUTO.NS`).
- Default to NSE; fall back to `.BO` only if the NSE yfinance lookup returns no price.

### 5.3 `MarketDataProvider` changes

- Constructor takes `market: Literal["US","IN"] = "US"`. `normalize_ticker()` applies the resolver for `IN`.
- Validation for `IN` (raise `DataQualityError` with a machine-readable code on failure):
  - `currency == "INR"`; price > 0; shares outstanding > 0
  - financial statements have at least `min_years` columns (default 3 for DCF)
  - no all-NaN rows among the rows `DCFInputs` needs
- Beta: **compute it yourself**: 3 years of weekly returns versus `^NSEI`, ignoring yfinance's `beta` field. Require ≥ 100 weekly observations. Otherwise return `beta=None` plus a warning, and let the pipeline fall back to a sector-median beta from the peer set.
- yfinance values are absolute INR. Label annual columns as fiscal years from the period-end date (never assume March).
- Sector: read `sector` / `industry`; feed it to the sector router (§10.1).

### 5.4 Peer universe

`find_peers()` must not depend on a yfinance screener for India. Introduce a `PeerUniverseProvider` interface with an `IndiaStaticUniverse` implementation reading `data/in_universe.csv` (`symbol, name, sector, industry, market_cap_inr, snapshot_date`). `find_peers(ticker_or_sector, market)` selects the provider by market. Inspect the current implementation first and keep the US behaviour unchanged.

### Phase 0 acceptance
- `RELIANCE`, `Reliance Industries`, `RELIANCE.NS`, and a BSE code each resolve correctly; an ambiguous name returns candidates.
- `POST /api/analyze -F ticker=RELIANCE` works end-to-end with `IN_*` set and fails cleanly with 503 when they are unset.
- US tests unchanged and passing.

---

## 6. Data models

New file `agent/aoc4/models.py`. All monetary values are absolute INR `Decimal`.

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class DocType(str, Enum):
    FORM = "form"
    FINANCIAL_STATEMENTS = "financial_statements"
    AUDITOR_REPORT = "auditor_report"
    BOARD_REPORT = "board_report"
    XBRL = "xbrl"
    ANNEXURE = "annexure"        # AOC-1, AOC-2, CSR report, MR-3, etc.
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
    LLM_ASSISTED = "llm_assisted"   # off by default, see §8.5


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
    # Profit and loss
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
    CAPEX = "capex"                          # purchase of PPE + intangibles (+CWIP), positive number
    CLOSING_CASH_PER_CFS = "closing_cash_per_cfs"
    DIVIDENDS_PAID = "dividends_paid"


class Provenance(BaseModel):
    doc_id: str
    page: int | None = None
    label_as_found: str | None = None     # row label text, or XBRL concept local name
    raw_value: str | None = None          # string exactly as extracted
    dash_as_zero: bool = False
    source: Source


class PeriodStatements(BaseModel):
    period_start: date | None = None
    period_end: date
    months: int
    basis: Basis
    framework: Framework
    source: Source                         # worst source among items used
    scale_detected: Literal["actual", "thousand", "lakh", "million", "crore"]
    scale_origin: Literal["statement_header", "xbrl_rounding", "user_override"]
    items: dict[Item, Decimal | None]
    provenance: dict[Item, Provenance] = Field(default_factory=dict)
    shares_outstanding: Decimal | None = None       # year-end, count of equity shares
    face_value_per_share: Decimal | None = None     # INR
    filing_doc_ids: list[str] = Field(default_factory=list)
    superseded_by: str | None = None                # set when a later filing restated this period

    @property
    def label(self) -> str:
        # "FY25" only when period_end is 31 March; otherwise "YE Dec-2024"
        ...


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    doc_type: DocType
    confidence: float
    classification_evidence: list[str]     # matched headings / keywords (short)
    basis: Basis = Basis.UNKNOWN
    period_end: date | None = None
    pages: int | None = None
    scanned: bool = False
    user_override: bool = False


class IssueSeverity(str, Enum):
    ERROR = "error"      # blocks valuation
    WARN = "warn"        # lowers confidence
    INFO = "info"


class ValidationIssue(BaseModel):
    code: str                              # e.g. "V1_BALANCE_SHEET_DOES_NOT_BALANCE"
    severity: IssueSeverity
    message: str
    period_end: date | None = None
    detail: dict[str, str] = Field(default_factory=dict)


class RedFlag(BaseModel):
    code: str                              # e.g. "AUD_QUALIFIED_OPINION"
    severity: Literal["high", "medium", "low", "info"]
    title: str
    evidence_quote: str                    # <= 200 chars, verbatim from the document
    doc_id: str
    page: int | None = None
    method: Literal["rule", "rule+classifier", "computed"]
    needs_review: bool = False


class ValuationMode(str, Enum):
    MARKET_RELATIVE = "market_relative"
    INTRINSIC_RANGE = "intrinsic_range"
    INTRINSIC_VS_REFERENCE = "intrinsic_vs_reference"
    COMPS_ONLY = "comps_only"
    UNSUPPORTED_SECTOR = "unsupported_sector"
    DISTRESSED = "distressed"
    EXTRACTION_ONLY = "extraction_only"


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
    low_inr: float
    mid_inr: float
    high_inr: float
    per_share_low: float | None = None
    per_share_mid: float | None = None
    per_share_high: float | None = None
    per_share_reliable: bool = True        # False if preference/CCPS/ESOP complexity detected
    dlom_applied: float | None = None      # discount for lack of marketability, if any


class DataQuality(BaseModel):
    score: Literal["high", "medium", "low"]
    primary_source: Source
    periods_available: int
    data_as_of: date
    staleness_days: int
    notes: list[str] = Field(default_factory=list)
```

### 6.1 Response model

Extend `AnalyzeResponse` (in `models/api.py`) by subclassing; do not change the base class's required fields.

```python
class AOC4AnalyzeResponse(AnalyzeResponse):
    valuation_mode: ValuationMode
    entity: EntityInfo
    equity_value: EquityValueRange | None = None
    documents: list[DocumentInfo]
    periods: list[PeriodSummary]           # compact per-FY table for display
    validation: list[ValidationIssue]
    red_flags_detailed: list[RedFlag]      # keep base `red_flags` (titles) populated for old clients
    data_quality: DataQuality
```

Notes:
- Check how `AnalyzeResponse.valuation` is typed. For unlisted companies `current_price` and `upside_pct` are `None`, so make them `Optional` in a backward-compatible way and confirm the frontend handles `null`.
- Extend the verdict type with `INCONCLUSIVE` and `NOT_APPLICABLE`; rating becomes `"N/A"`. Grep all consumers of the verdict (`_derive_verdict`, the judge agent output model, the frontend colour map) before adding values.

---

## 7. File and module layout

### New
```
agent/aoc4/
  __init__.py
  models.py              # §6
  bundle.py              # safe unzip, file typing, size limits, grouping
  classifier.py          # document classification
  units.py               # unit detection, scale conversion, INR formatting
  fiscal.py              # period parsing, FY labels, period-length checks
  numbers.py             # Indian number parser
  xbrl_reader.py         # lxml-based fact extractor (no network)
  xbrl_mapping.yaml      # concept → Item candidates (seeded from real samples, §16)
  pdf_statements.py      # statement detection + table extraction (Schedule III)
  ocr.py                 # scanned-page detection + OCR wrapper
  label_map.py           # Schedule III label synonyms → Item (Appendix A)
  sections.py            # India section detection → FilingSection[]
  merge.py               # multi-filing reconciliation (latest filing wins)
  validation.py          # V1…V10
  redflags.py            # rules + closed-set classifier
  to_dcf.py              # PeriodStatements[] → DCFInputs
agent/valuation/
  unlisted.py            # unlevered beta from peers, relever, DLOM, cost of debt
  sector_router.py       # financial-sector detection and routing
  verdict_in.py          # derive_verdict_in()
agent/data/
  in_symbols.py          # Phase 0
  in_universe.py         # Phase 0
agent/config/markets.py  # Phase 0
agent/pipeline/aoc4.py   # AOC4Pipeline orchestrating stages 0–6
agent/api/aoc4_routes.py # new router
scripts/
  dump_xbrl_concepts.py  # discovery tool for §16
  classify_bundle.py     # CLI: classify a folder of files
tests/aoc4/              # see §14
data/in_equities_nse.csv, data/in_scrips_bse.csv, data/in_universe.csv
docs/aoc4_findings.md, docs/decisions.md
```

### Modified (minimal, additive)
- `models/api.py`: optional fields; new verdict values.
- `agents/analysis.py`, `agents/debate.py`: accept a prompt variant keyed by market and valuation mode (INR, crore, Ind AS vocabulary, "no price" framing).
- `agents/ResearchDeps`: add optional `aoc4_context: AOC4Context | None = None`.
- `valuation/dcf.py`: only add optional `DCFInputs` fields with defaults that preserve current output (see §10.3).
- `valuation/synthesis.py`: add the mode-aware confidence rules (§10.5).
- `api/server.py`: include the new router; extend `/api/health`.
- `frontend/src/App.jsx`: §12.

---

## 8. Component specifications

### 8.1 Bundle ingestion (`bundle.py`)

Input: list of `UploadFile` (any mix of PDF, XML/XBRL, ZIP, HTML).

- **Limits** (configurable via `Settings`): max 40 files, 150 MB total uncompressed, 400 pages per PDF, zip depth 1, max compression ratio 100:1.
- **Allowed extensions:** `.pdf .xml .xbrl .htm .html .zip`. Verify magic bytes, not just extension. Reject everything else with `UNSUPPORTED_FILE_TYPE`.
- **Zip safety:** reject entries with absolute paths or `..` components (zip-slip); ignore symlinks; extract into `upload/{request_id}/`; never execute anything.
- Assign each file a stable `doc_id` (`d01`, `d02`, …).
- **Cleanup:** delete `upload/{request_id}/` when the request finishes (`try/finally`). Do not log document contents.
- Parsing runs in a worker thread (`run_in_threadpool`) with an overall timeout (default 120 s); on timeout return 504 with the stage reached.

### 8.2 Classifier (`classifier.py`)

Deterministic first. For each document, read the first N (default 3) pages' text plus the filename. Return `DocumentInfo` with `doc_type`, `confidence`, and the evidence strings.

| Type | Strong signals (case-insensitive, any order) |
|------|----------------------------------------------|
| `xbrl` | XML root element in the `xbrli` instance namespace |
| `form` | "Form No. AOC-4", "Form AOC-4", "AOC-4 CFS", "Section 137" |
| `auditor_report` | "Independent Auditor's Report" / "Auditors' Report" as a heading; "Report on the Audit of the … Financial Statements" |
| `board_report` | "Board's Report" / "Directors' Report" heading; "Your Directors have pleasure in presenting" |
| `financial_statements` | headings "Balance Sheet as at", "Statement of Profit and Loss for the year ended", "Cash Flow Statement", "Notes to the Financial Statements" |
| `annexure` | "Form No. AOC-2", "Form AOC-1", "Annual Report on CSR", "Form No. MR-3" |

- A single PDF may contain several parts (a combined PDF with auditor report + statements + notes). So classification is **per page range**, not just per file: scan each page's heading and emit `DocumentInfo` entries with `page_start`/`page_end` (add those two optional fields to `DocumentInfo`). Downstream code works on page ranges.
- Detect `basis`: "Consolidated Financial Statements" / "Consolidated Balance Sheet" → `CONSOLIDATED`; otherwise `STANDALONE` if "Standalone" appears or no "Consolidated" appears; else `UNKNOWN`.
- Detect `framework`: "Ind AS" / "Indian Accounting Standards" in the basis-of-preparation text → `IND_AS`; "Accounting Standards" prescribed under Section 133 with no Ind AS mention, or Division I line items such as "Shareholders' funds" → `INDIAN_GAAP`.
- Detect `period_end` from "as at / for the year ended <date>" (see §8.7).
- If confidence < 0.6, mark the document `OTHER` and add a `WARN`. The API accepts `doc_overrides` (JSON map `filename → DocType`), and overridden docs get `user_override=True`.
- Optional LLM labeller for low-confidence pages: **closed set** (the `DocType` values only), output validated against the enum, `confidence` capped at 0.7, evidence recorded as `llm`. Off unless `ALLOW_LLM_CLASSIFIER=true`.

### 8.3 XBRL reader (`xbrl_reader.py`)

**Approach:** parse the instance with `lxml`. No taxonomy download, no network. Arelle is optional (used only in a diagnostic script).

1. Parse `xbrli:context` elements: id, period (instant, or startDate/endDate), and whether the context has dimensional members (`xbrldi:explicitMember` / `typedMember` in segment or scenario). **Primary statement values use only contexts with no dimensions.**
2. Parse `xbrli:unit` elements; keep only monetary INR units for money items and pure/shares units for counts.
3. Parse facts: any element with `contextRef` + `unitRef`; keep local name, namespace, value, `decimals`, `contextRef`.
4. Select the **current period** and **prior period** contexts by matching the document's reporting dates (duration contexts of about 12 months for P&L/CF; instant at period end for BS).
5. Map concepts → `Item` via `xbrl_mapping.yaml` (list of candidate concept local names per Item, first present wins; if two candidates are present with different values, raise `AMBIGUOUS_CONCEPT` as a WARN and use the first).
6. Detect rounding/scale: see §16 OQ-1. Record `scale_origin="xbrl_rounding"`.

`xbrl_mapping.yaml` seed (names are placeholders and **must be replaced with the real concept names found by `scripts/dump_xbrl_concepts.py`** on sample files):

```yaml
revenue_from_operations: [ "<concept-1>", "<concept-2>" ]
total_assets: [ "<concept>" ]
# ... one entry per Item. Concept names are NOT to be invented; take them from real filings.
```

`scripts/dump_xbrl_concepts.py <file>`: prints every distinct concept (namespace, local name), its non-dimensional value for each context, units and decimals, sorted by magnitude. Use it to build the mapping and OQ-1's answer.

### 8.4 Indian number parser (`numbers.py`)

`parse_indian_number(text, *, context="money") -> ParsedNumber(value: Decimal | None, dash_as_zero: bool)`

| Input | Output |
|-------|--------|
| `1,23,456.78` | `123456.78` |
| `12,34,56,789` | `123456789` |
| `(1,234.50)` | `-1234.50` |
| `-1,234` or `(-1,234)` | `-1234` |
| `—`, `–`, `-`, `Nil`, `NIL` in a table value cell | `0`, `dash_as_zero=True` |
| `₹ 1,234`, `Rs. 1,234`, `INR 1,234` | `1234` |
| `1,234*`, `1,234 (a)`, `1,234¹` | `1234` (strip footnote markers) |
| `12.5%` | rejected in `money` context |
| `3.1.2` | rejected (looks like a note reference) |

Rules:
- Strip spaces, NBSP, and thin spaces inside numbers (`1 23 456`).
- Never treat a dash as zero in a label cell.
- Return `None` for unparseable cells; count them for the validation report.

`format_inr(value, unit="crore", decimals=2)` formats with Indian digit grouping (`12,34,567.89`) for display only.

### 8.5 PDF statements extraction (`pdf_statements.py`)

For each page range classified `financial_statements`:

1. **Detect the statement type** by heading: balance sheet, profit and loss, cash flow, changes in equity, notes. Multiple statements can share one page range.
2. **Detect unit** from the nearest header text within the first 15 lines of the page, e.g. `(₹ in Lakhs)`, `(Rs. in crore)`, `(INR in Millions)`, `(Amount in ₹ '000)`, "all amounts in Indian Rupees in lakhs, unless otherwise stated", "(Amount in Rupees)" = actual. Unit conflicts between statement pages → `UNIT_AMBIGUOUS` (ERROR) unless the user passes `unit_override`.
3. **Detect the column layout** with pdfplumber's table/words APIs:
   - find the header row containing at least two date-like strings (`31 March 2025`, `March 31, 2025`, `31.03.2025`, `31st March, 2025`)
   - **drop the "Note" / "Notes" / "Note No." column**: its small integers (e.g. `12`, `3.1`) must never be read as values
   - current period is normally the first value column, but decide by header dates, not position
4. **Extract rows:** label text + numeric cells for the 2 value columns. Handle multi-line labels (wrapped label rows with no numbers belong to the next row that has numbers). Handle sub-total / total rows.
5. **Map labels → `Item`** via `label_map.py` (normalise: lowercase, strip punctuation and note references, collapse whitespace; exact synonym match, then fuzzy match ≥ 0.92 with `rapidfuzz`). Unmapped rows are kept in a `unmapped_rows` diagnostic list on the period (count visible in `data_quality.notes`). Do not drop silently.
6. **Derived items** (where the statement gives components but not totals): sum with provenance noting `derived`.
7. **Scanned pages:** a page whose extractable text is below ~100 characters is "scanned". If any statement page is scanned:
   - `ocr.py` runs OCR (`ocrmypdf`/Tesseract) on those pages only, then re-runs steps 1–6 on the OCR text layer; `source=PDF_OCR`.
   - If OCR is not installed or disabled, return `OCR_UNAVAILABLE` (422) with install instructions.
   - **OCR numbers must pass V1–V3 (validation) or the result is an ERROR, not a WARN.** Identity checks are the only safety net against OCR digit errors.
8. **Optional LLM-assisted extraction fallback** (`ALLOW_LLM_EXTRACTION=false` by default): if rule-based extraction fails for a statement, an LLM may propose `{label, current, prior}` rows. Every proposed value is accepted **only if the exact digit string appears in the source page text**, and the full statement must pass V1–V3. Mark `source=LLM_ASSISTED`, cap `data_quality` at `low`. This is the only place an LLM touches numbers, and it never bypasses validation.

### 8.6 Section detection and RAG (`sections.py`)

Reuse the existing `FilingSection` and `BM25Retriever`. Add optional fields `source_doc_id`, `page_start`, `page_end`, and extend the section type enum with India values:

`AUDITOR_REPORT`, `CARO_ANNEXURE`, `BOARD_REPORT`, `SIGNIFICANT_ACCOUNTING_POLICIES`, `NOTES_TO_ACCOUNTS`, `RELATED_PARTY_NOTE`, `CONTINGENT_LIABILITIES_NOTE`, `BORROWINGS_NOTE`, `BALANCE_SHEET`, `PROFIT_AND_LOSS`, `CASH_FLOW`, `ANNEXURE_AOC2`.

- Split by heading detection (regex list per type), not by fixed "Item N" structure.
- Chunk long sections (~800–1200 tokens with ~100 overlap) and keep `section_type` on every chunk.
- Skip promotional / boilerplate pages if present (chairman's letter, awards).
- `FilingQAIgent` answers must cite `doc_id` and page.

### 8.7 Units, fiscal periods (`units.py`, `fiscal.py`)

```python
UNIT_FACTORS = {"actual": 1, "thousand": 10**3, "lakh": 10**5, "million": 10**6, "crore": 10**7}
```

- Scale-origin priority: `user_override` > statement header text > XBRL rounding fact. If header and XBRL disagree, return `UNIT_AMBIGUOUS` (ERROR) and ask for `unit_override`.
- Period parsing: accept `31 March 2025`, `March 31, 2025`, `31.03.2025`, `31/03/2025`, `31st March, 2025`. `months` is computed from start and end dates. If the period is not 12 months (±15 days), set the period aside as `NON_STANDARD_PERIOD` (WARN) and exclude it from growth/margin history. Do not annualise.
- Labels: `FY{yy}` when `period_end` is 31 March; otherwise `YE {Mon}-{yyyy}`.
- Staleness: `staleness_days = today - latest period_end`. If it exceeds `max_financials_age_days`, add a WARN and cap confidence at Medium.

### 8.8 Multi-filing reconciliation (`merge.py`)

One AOC-4 bundle contains current and prior-year columns, so it yields **two** periods. A DCF needs more history, so the endpoint accepts bundles for several years in one request (files grouped by detected `period_end`).

- Key periods by `(period_end, basis)`.
- If the same period appears in two filings, the **later filing's value wins** (restatement). Record `superseded_by` on the old one and add an INFO issue if any key item differs by > 0.5%.
- Never merge across `basis` or across `framework` without an explicit WARN (a framework change such as GAAP → Ind AS breaks comparability).
- Sort ascending by `period_end`. Confirm the ordering convention that `DCFInputs` expects (§0 item 1) and convert in `to_dcf.py`.

### 8.9 Validation (`validation.py`)

Each check yields `ValidationIssue`. Tolerance is `max(2 units at the declared scale, 0.1% of the larger operand)` unless noted.

| ID | Check | Severity |
|----|-------|----------|
| V1 | `total_assets == total_equity_and_liabilities` (and `total_assets == total_equity + total liabilities` if derivable) | ERROR |
| V2a | `revenue_from_operations + other_income ≈ total_income` | WARN (ERROR if source is OCR) |
| V2b | `total_income − total_expenses ≈ profit_before_tax − exceptional_items` (sign conventions per Schedule III) | WARN (ERROR if OCR) |
| V2c | `profit_before_tax − tax_expense ≈ profit_after_tax` (before discontinued ops/OCI) | WARN (ERROR if OCR) |
| V3 | `closing_cash_per_cfs ≈ cash_and_equivalents` (note: CFS may net bank overdrafts; downgrade to INFO if difference equals a disclosed overdraft) | WARN (ERROR if OCR) |
| V4 | All periods used share one `basis` | ERROR |
| V5 | Prior-year column of the later filing vs current column of the earlier filing (restatement detection) | INFO / WARN if material |
| V6 | Magnitude sanity: `revenue / total_assets` between 0.01 and 50; `equity_share_capital > 0`; non-negative where required | WARN |
| V7 | Period length 12 ± 0.5 months | WARN (period excluded) |
| V8 | History depth: ≥ 3 periods for DCF with growth/margin estimates | WARN, and `valuation_mode=COMPS_ONLY` if fewer than 3 (or `EXTRACTION_ONLY` if comps are also unavailable) |
| V9 | If XBRL and PDF both parsed: key totals agree within tolerance | WARN (prefer XBRL, record mismatch) |
| V10 | Entity identity: CIN in the request matches the CIN in the form/documents; company name approximately matches | ERROR on CIN mismatch, WARN on name |
| V11 | Staleness (§8.7) | WARN |
| V12 | Unparsed/unmapped row ratio on any statement > 25% | WARN |

Any ERROR blocks the valuation stages. The response is HTTP 422 with `error_code` set to the first ERROR's code and the full `validation` list attached. When everything was extracted but valuation is not permitted by policy (modes F/G), return HTTP 200 with `INCONCLUSIVE`.

### 8.10 Red flags (`redflags.py`)

Two-step design to avoid false positives on boilerplate:
1. **Locate** with deterministic, **heading-anchored** rules on the relevant `FilingSection`.
2. **Classify polarity** where needed using either a negation-aware rule or the closed-set LLM classifier (`{"adverse","non_adverse","not_applicable","unclear"}`, validated). `unclear` → `needs_review=True`.

Audit reports contain boilerplate that names the very things being flagged (the "going concern" and "modified opinion" language in the auditor's responsibilities paragraph appears in **every** clean report). **Match on section headings, never on a bare keyword anywhere in the report.** A clean report fixture must produce zero flags (§14).

| Code | Trigger | Severity |
|------|---------|----------|
| `AUD_QUALIFIED_OPINION` | heading "Qualified Opinion" / "Basis for Qualified Opinion" | high |
| `AUD_ADVERSE_OPINION` | heading "Adverse Opinion" / "Basis for Adverse Opinion" | high |
| `AUD_DISCLAIMER` | heading "Disclaimer of Opinion" | high |
| `AUD_GOING_CONCERN` | heading "Material Uncertainty Related to Going Concern" | high |
| `AUD_EMPHASIS_OF_MATTER` | heading "Emphasis of Matter" | medium |
| `AUD_KEY_AUDIT_MATTERS` | heading "Key Audit Matters": list the matter titles | info |
| `AUD_FRAUD_143_12` | text referencing reporting of fraud under Section 143(12) *and* adverse polarity | high |
| `CARO_DEFAULT_ON_BORROWINGS` | CARO clause on default in repayment of loans/borrowings, adverse polarity | high |
| `CARO_FRAUD` | CARO clause on fraud noticed/reported, adverse polarity | high |
| `CARO_CASH_LOSSES` | CARO clause on cash losses in the year / preceding year, adverse polarity | medium |
| `CARO_MATERIAL_UNCERTAINTY` | CARO clause on material uncertainty in meeting liabilities, adverse polarity | high |
| `CARO_STATUTORY_DUES` | CARO clause on undisputed statutory dues outstanding > 6 months | medium |
| `CARO_RELATED_PARTY_NONCOMPLIANCE` | CARO related-party clause adverse | medium |
| `CARO_AUDITOR_RESIGNATION` | CARO clause on resignation of statutory auditors, with issues raised | medium |
| `CARO_UNSPENT_CSR` | CARO clause on unspent CSR amount not transferred | low |
| `AUDITOR_CHANGED` | statutory auditor firm name or firm registration number differs between periods | medium |
| `NEGATIVE_NET_WORTH` | `total_equity < 0` (computed) | high |
| `LOSS_MAKING_MULTI_YEAR` | PAT < 0 in the latest 2+ periods (computed) | medium |
| `NEGATIVE_CFO_MULTI_YEAR` | CFO < 0 in the latest 2+ periods (computed) | medium |
| `LOW_INTEREST_COVERAGE` | (PBT + finance costs) / finance costs < 1.5 (computed; threshold in config) | medium |
| `NEGATIVE_WORKING_CAPITAL_GAP` | current liabilities exceed current assets by > 50% of current liabilities (computed) | low |
| `HIGH_RELATED_PARTY_SHARE` | related-party transactions / revenue above threshold (config default 10%); needs the RPT note or AOC-2 table parsed | medium, `needs_review=True` |
| `HIGH_CONTINGENT_LIABILITIES` | contingent liabilities / net worth above threshold (config default 20%) | medium, `needs_review=True` |
| `CCPS_OR_PREFERENCE_PRESENT` | preference share capital or compulsorily convertible instruments present | info (affects per-share reliability) |

CARO clause numbering follows the CARO 2020 order, but **locate clauses by their subject text as well as the number**, since layouts vary and numbering may differ in older or sector-specific orders. Treat "Not applicable", "Nil", and "No such matters" as `not_applicable`.

Each `RedFlag` carries a verbatim `evidence_quote` (≤ 200 chars), `doc_id`, and `page`. Items marked `needs_review` are displayed with a "verify manually" badge and never alone drive confidence.

### 8.11 Statements → `DCFInputs` (`to_dcf.py`)

Definitions (all configurable, documented in the output's `dcf_assumptions`):

- `revenue_history` = `REVENUE_FROM_OPERATIONS` per eligible period (12-month periods only).
- **EBITDA** = `PROFIT_BEFORE_TAX − EXCEPTIONAL_ITEMS + FINANCE_COSTS + DEPRECIATION_AMORTISATION − OTHER_INCOME` (setting `EBITDA_INCLUDES_OTHER_INCOME=false` is the default). Apply the sign convention carefully: exceptional *gains* are subtracted, *losses* added back; test with fixtures.
- `short_term_debt` = `BORROWINGS_CURRENT` (+ `CURRENT_MATURITIES_LTD` if reported separately and not already inside current borrowings; detect double-counting by comparing to the borrowings note if available, else WARN).
- `long_term_debt` = `BORROWINGS_NON_CURRENT`.
- Lease liabilities (Ind AS 116) are included in debt when `INCLUDE_LEASES_IN_DEBT=true` (default true for Ind AS companies, false for Indian GAAP).
- `cash_and_equivalents` = `CASH_AND_EQUIVALENTS + OTHER_BANK_BALANCES` (config: `INCLUDE_OTHER_BANK_BALANCES=true`; optionally `+ CURRENT_INVESTMENTS` if `TREAT_CURRENT_INVESTMENTS_AS_CASH=true`, default false).
- `net_debt` = debt − cash as defined above.
- `shares_outstanding`: listed → latest from yfinance (flag if it differs from AOC-4 year-end by > 5%); unlisted → `EQUITY_SHARE_CAPITAL / face_value_per_share`, where the face value is parsed from the share-capital note (e.g. "equity shares of ₹10 each"). If it cannot be parsed, `shares_outstanding=None` and the output reports equity value only.
- `tax_rate`: effective rate (`TAX_EXPENSE / PBT`) averaged over eligible periods if all periods are profitable and the rate lies within [10%, 40%]; otherwise `IN_DEFAULT_TAX_RATE`.
- `beta`, `debt_ratio`: see §10.2.
- `ticker`: populate with the CIN for unlisted companies so `DCFInputs` need not change its required fields. Add optional `identifier_type` and `currency` fields with defaults preserving US behaviour.
- Optionally pass `capex_history`, `depreciation_history`, `nwc_history` as new optional `DCFInputs` fields, used only if `dcf.py` is extended to consume them (§10.3).

### 8.12 LLM prompts and narration guard

- Prompt variants for India: amounts in ₹ crore with Indian grouping, Ind AS vs GAAP vocabulary, an explicit "this company is unlisted; there is no market price" paragraph when relevant.
- Filing text is **untrusted data**: wrap in delimiters, instruct the model to ignore any instructions found inside, and make all agent tools read-only.
- **Numeric guard (recommended):** after narration, extract every number from `reasoning`, `bull_case`, `bear_case`, etc. and check it against the set of computed values (formatted in the units used). Numbers not found in that set are either removed or the response is regenerated once; if it still fails, return the deterministic summary only and set a WARN. This enforces "numbers by code".

---

## 9. API contract

### 9.1 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/aoc4/extract` | Phase 1 deliverable. Bundle → classification, extracted statements, validation. No valuation. |
| `POST` | `/api/aoc4/analyze` | Full pipeline (§4.2) → `AOC4AnalyzeResponse`. |
| `GET` | `/api/aoc4/config` | Which `IN_*` settings are present/missing; OCR availability; feature flags. |
| `GET` | `/api/health` | Existing; add `india_config_ready`, `ocr_available`. |

### 9.2 Request (multipart form)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `files` | file[] | yes | PDFs, XML/XBRL, zip. Multiple fiscal years allowed. |
| `cin` | str | for unlisted | 21-char CIN, validated with `^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$`. The first letter (`L`/`U`) is only a hint for listed/unlisted; the user's `entity_type` wins. |
| `ticker` | str | for listed | Resolved by §5.2. |
| `entity_type` | `listed|unlisted|auto` | no | default `auto`: ticker present → listed; else CIN hint. |
| `basis` | `standalone|consolidated|auto` | no | default `auto` (use what the documents say; if both present, default standalone and WARN, or require explicit choice when `STRICT_BASIS=true`). |
| `fiscal_year` | str | no | default: latest detected. |
| `unit_override` | `actual|thousand|lakh|million|crore` | no | overrides detection. |
| `sector_override` | str | no | closed list from `in_universe.csv`. |
| `reference_price` | float | no | INR per share (listed overrides the market price only when explicitly passed; unlisted enables mode E). |
| `reference_equity_value` | float | no | INR absolute (unlisted, mode E, e.g. last funding round). |
| `doc_overrides` | JSON str | no | `{"file.pdf": "auditor_report"}`. |

### 9.3 Example

```bash
# Unlisted company, XBRL + PDFs (fictional CIN)
curl -X POST http://localhost:8000/api/aoc4/analyze \
  -F "cin=U74999KA2015PTC080000" \
  -F "entity_type=unlisted" -F "basis=standalone" \
  -F "files=@FY25_financial_statements.pdf" \
  -F "files=@FY25_auditor_report.pdf" \
  -F "files=@FY25_xbrl.xml" \
  -F "files=@FY24_financial_statements.pdf" \
  -F "files=@FY24_auditor_report.pdf"

# Listed company, zip bundle
curl -X POST http://localhost:8000/api/aoc4/analyze \
  -F "ticker=RELIANCE" -F "files=@bundle.zip"
```

### 9.4 Response (unlisted, abbreviated)

```json
{
  "verdict": "NOT_APPLICABLE",
  "rating": "N/A",
  "valuation_mode": "intrinsic_range",
  "entity": {"cin": "U74999KA2015PTC080000", "listed": "unlisted", "framework": "ind_as", "basis": "standalone"},
  "equity_value": {"low_inr": 0, "mid_inr": 0, "high_inr": 0, "per_share_reliable": true, "dlom_applied": 0.20},
  "valuation": {"fair_value_low": null, "fair_value_high": null, "fair_value_mid": null,
                "current_price": null, "upside_pct": null, "confidence": "Low"},
  "periods": [{"label": "FY25", "period_end": "2025-03-31", "source": "xbrl"}],
  "validation": [{"code": "V11_STALE", "severity": "warn", "message": "..."}],
  "red_flags": ["Emphasis of Matter paragraph in auditor's report"],
  "red_flags_detailed": [{"code": "AUD_EMPHASIS_OF_MATTER", "severity": "medium", "evidence_quote": "...", "doc_id": "d02", "page": 4, "method": "rule", "needs_review": false}],
  "data_quality": {"score": "medium", "primary_source": "xbrl", "periods_available": 3, "data_as_of": "2025-03-31", "staleness_days": 190},
  "stages": [{"stage": "0. BUNDLE", "status": "complete", "summary": "5 files, 2 periods"}],
  "sources": ["d01 p.12–31", "d03 (xbrl)"]
}
```
(Zeros above stand for computed values, not literals.)

### 9.5 Error codes (HTTP 422 unless noted)

`UNSUPPORTED_FILE_TYPE`, `BUNDLE_TOO_LARGE` (413), `NO_FINANCIAL_STATEMENTS`, `OCR_UNAVAILABLE`, `UNIT_AMBIGUOUS`, `BALANCE_CHECK_FAILED`, `BASIS_MIXED`, `CIN_MISMATCH`, `CIN_INVALID`, `AMBIGUOUS_SYMBOL` (returns candidates), `INSUFFICIENT_HISTORY` (only when no fallback mode is possible), `CONFIG_MISSING` (503), `TIMEOUT` (504). Always include the `validation` list and `stages` reached.

---

## 10. Valuation behaviour by mode

### 10.1 Sector router (`valuation/sector_router.py`)

Order of evidence: user `sector_override` → yfinance `sector`/`industry` (listed) → closed-set classification of the business description in the Board's Report (labels from `in_universe.csv`; output validated; `sector_source="llm_closed_set"`) → CIN's NIC code (`sector_source="nic_hint"`; it reflects the industry at incorporation, so treat it as a hint only).

Financial-sector detection (banks, NBFCs, insurers, housing finance, broking and similar): by sector label, or by text signals such as "Non-Banking Financial Company", "Reserve Bank of India Act, 1934", "prudential norms", "Insurance Act", or use of Schedule III Division III. Result: `valuation_mode=UNSUPPORTED_SECTOR`, verdict `INCONCLUSIVE`, explanation: "FCFF DCF is not meaningful where debt is operating capital; book-value/ROE-based valuation is not implemented."

### 10.2 Cost of capital for unlisted companies (`valuation/unlisted.py`)

- **Peers:** select ≥ 5 listed peers from the India universe by sector/industry and closest size. If fewer than 3 available → `COMPS_ONLY` is also impossible → `EXTRACTION_ONLY`.
- **Beta:** compute each peer's beta vs `^NSEI` (§5.3), unlever with the peer's own D/E and tax rate (`β_u = β_L / (1 + (1−t)·D/E)`), take the **median** `β_u`, relever at the target D/E.
- **Target capital structure:** config `UNLISTED_CAPITAL_STRUCTURE = peer_median | book | blend`. Default `peer_median` when ≥ 3 peers, else `book`. Print the choice in `dcf_assumptions`.
- **Cost of debt:** effective rate = finance costs / average borrowings over the period, bounded to `[risk_free_rate + 0.5%, risk_free_rate + 12%]`; if borrowings are negligible, use `risk_free_rate + spread` from config.
- **Illiquidity:** apply a discount for lack of marketability to equity value, config `UNLISTED_DLOM` (default `0.20`, a placeholder for the user to review). **Do not also add a size premium to the discount rate**, to avoid double counting. The applied value is echoed in `EquityValueRange.dlom_applied` and in `dcf_assumptions`.
- Everything above is surfaced as an explicit assumption; the response must make it easy to see which numbers are user-adjustable.

### 10.3 DCF/comps changes

- Do not change FCFF math for the US path. Add optional `DCFInputs` fields (all defaulting to `None`/US behaviour): `currency`, `identifier_type`, `capex_history`, `depreciation_history`, `nwc_history`. If `dcf.py` currently derives capex/D&A/NWC from assumptions, use the actual historical ratios only when the optional lists have ≥ 3 points, and record "used actual history" in the assumptions.
- `multiples.compute_comps()` for unlisted: apply peer median EV/EBITDA and P/E to the target's metrics; skip P/B unless book equity > 0; EV → equity bridge with the net debt definition in §8.11; then DLOM.
- Sensitivity matrix: unchanged shape (growth × WACC); for unlisted, the output is the equity-value grid rather than per-share.

### 10.4 Per-share reliability

If `PREFERENCE_SHARE_CAPITAL > 0`, or the notes mention compulsorily convertible preference shares / ESOP pool / warrants / convertible debentures, set `per_share_reliable=False`, emit `CCPS_OR_PREFERENCE_PRESENT`, and keep the primary output at **total equity value**. Do not compute per-share values from equity capital alone in that case.

### 10.5 Confidence and verdict (`verdict_in.py`)

Existing thresholds (±15% around current price) remain for modes B, C, E. New gating, applied only when `market=IN` (setting `VERDICT_GATING_ENABLED=true`):

```python
def derive_verdict_in(v: ValuationResult, mode: ValuationMode,
                      flags: list[RedFlag], issues: list[ValidationIssue], cfg) -> VerdictResult:
    if mode in (UNSUPPORTED_SECTOR, DISTRESSED, EXTRACTION_ONLY):
        return VerdictResult("INCONCLUSIVE", "N/A", reason=...)
    if mode == INTRINSIC_RANGE:
        return VerdictResult("NOT_APPLICABLE", "N/A", reason="No market price for an unlisted company")
    if v.dcf_mid and v.comps_mid:
        divergence = abs(v.dcf_mid - v.comps_mid) / ((v.dcf_mid + v.comps_mid) / 2)
        if divergence > cfg.max_method_divergence:       # default 0.50
            return VerdictResult("INCONCLUSIVE", "N/A", reason="DCF and comps disagree materially")
    # otherwise the existing ±15% rule on fair_value_mid vs reference/current price
```

Confidence rules (take the lowest that applies):

| Condition | Confidence |
|-----------|------------|
| Unlisted | never above Medium |
| Any ERROR validation issue | verdict blocked |
| Any `high` red flag | Low |
| Source is OCR or LLM-assisted | Low |
| < 3 eligible periods | Low |
| Staleness > `max_financials_age_days` | Medium |
| DCF and comps within 25% and no WARN-level validation issues | Medium (High allowed only for listed, XBRL or clean PDF source) |
| Otherwise | Low |

`DISTRESSED` is entered when `AUD_GOING_CONCERN`, `AUD_ADVERSE_OPINION`, or `AUD_DISCLAIMER` is present, or `NEGATIVE_NET_WORTH` combined with negative CFO. In that mode the model stages are skipped and the response explains why. The user may force the model with `force_valuation=true` (default false), which keeps confidence at Low.

---

## 11. Output and display conventions

- All API monetary fields are absolute INR floats. Add a `display` block with `unit` (`crore` by default) and formatted strings using Indian grouping (`₹ 1,23,456.78 Cr`).
- The reasoning text states: period end, basis, framework, source (XBRL/PDF/OCR), unit detected, and staleness.
- The disclaimer for unlisted output states that no market price exists and the range reflects modelling assumptions including an illiquidity discount.
- Sources list cites `doc_id` and page ranges, never raw file paths.

---

## 12. Frontend changes (`App.jsx`, `App.css`)

1. **Market toggle:** `US | India`. India shows the AOC-4 inputs.
2. **Inputs (India):**
   - Entity type (auto / listed / unlisted), ticker or CIN (validated client-side with the CIN regex)
   - Multi-file drag-and-drop (PDF, XML, ZIP); list of added files with remove buttons
   - Optional: basis, unit override, reference price / reference equity value
3. **Classification review panel** (shown after upload or in the result): table of `documents` with detected type, basis, period end, confidence, and a dropdown to override the type; "Re-run" resends with `doc_overrides`.
4. **Verdict banner:** existing colours plus grey for `INCONCLUSIVE` / `NOT_APPLICABLE`. Show `valuation_mode` as a label under the verdict.
5. **Metrics row:** for unlisted show Equity Value (low/mid/high in ₹ Cr) and DLOM instead of price/upside; hide the metric boxes that are `null`.
6. **New collapsible sections:** Data Quality (source, periods, staleness), Validation Issues (grouped by severity), Red Flags (with evidence quotes, doc/page, "verify manually" badge), Period Table (FY columns with key line items).
7. Handle `422` errors by showing the `error_code`, the validation list, and what the user can do (e.g. provide `unit_override`, upload the missing statement).
8. Check that the stage list, colour map, and metric boxes tolerate unknown/new values.

---

## 13. Configuration and dependencies

### Settings (add to `Settings`; all new, all with defaults except `IN_*` market inputs)
```
IN_RISK_FREE_RATE, IN_EQUITY_RISK_PREMIUM            # required for DCF, no default
IN_DEFAULT_TAX_RATE=0.2517
IN_TERMINAL_GROWTH_CAP=0.05
IN_MAX_FINANCIALS_AGE_DAYS=456
UNLISTED_DLOM=0.20
UNLISTED_CAPITAL_STRUCTURE=peer_median
VERDICT_GATING_ENABLED=true
MAX_METHOD_DIVERGENCE=0.50
EBITDA_INCLUDES_OTHER_INCOME=false
INCLUDE_LEASES_IN_DEBT=auto
INCLUDE_OTHER_BANK_BALANCES=true
TREAT_CURRENT_INVESTMENTS_AS_CASH=false
STRICT_BASIS=false
ALLOW_LLM_CLASSIFIER=false
ALLOW_LLM_EXTRACTION=false
OCR_ENABLED=true
MAX_UPLOAD_FILES=40
MAX_UPLOAD_MB=150
MAX_PDF_PAGES=400
PIPELINE_TIMEOUT_S=120
RED_FLAG_RPT_THRESHOLD=0.10
RED_FLAG_CONTINGENT_THRESHOLD=0.20
RED_FLAG_COVERAGE_THRESHOLD=1.5
```

### Python dependencies (uv)
```
uv add lxml rapidfuzz ocrmypdf pytesseract
uv add --optional xbrl arelle-release      # diagnostics only
```
`pdfplumber`, `pydantic`, `python-multipart`, `rank-bm25` already exist.

### System packages (OCR path, Debian/Ubuntu-based)
```
sudo apt install tesseract-ocr poppler-utils ghostscript
```
`/api/aoc4/config` reports `ocr_available` by checking for the `tesseract` binary at startup.

---

## 14. Testing plan

Create `tests/aoc4/` with these groups. Where real filings are needed, **the user supplies sample bundles** (§16); do not commit documents you are not allowed to redistribute. Generate synthetic fixtures for everything else.

### 14.1 Unit tests
- `numbers.py`: every row in the §8.4 table, plus `1 23 456`, NBSP-separated values, and `3.1.2` rejection.
- `units.py`: header strings in all unit spellings (lakh/lakhs/lac, crore/crores/Cr, million/mn, `'000`, "Amount in Rupees"); conflicting units → `UNIT_AMBIGUOUS`; `format_inr` grouping.
- `fiscal.py`: all date formats; 12-month vs 9-month and 15-month periods; FY label for 31 March and 31 December.
- CIN validation: valid and invalid examples (wrong length, lowercase, bad state code format).
- `bundle.py`: zip-slip entry `../../x`, symlink entry, over-size, over-ratio, nested zip, wrong magic bytes.
- `classifier.py`: synthetic PDFs (generated with reportlab) containing each heading; combined PDF with multiple parts split into page ranges; low-confidence handling and overrides.
- `label_map.py`: every Appendix A synonym; unmapped row diagnostics.
- `xbrl_reader.py`: synthetic instance with dimensional and non-dimensional facts (dimensional facts must be ignored for primary values), two periods, duplicate facts.
- `pdf_statements.py`: synthetic statement with a **Note column** (must not be read as values), wrapped multi-line labels, parentheses negatives, dash-as-zero, two date columns in reversed order.
- `validation.py`: each V-check with a passing case and a failing case; OCR source escalating WARN to ERROR.
- `merge.py`: restated prior year (later filing wins), basis mismatch, framework change.
- `to_dcf.py`: EBITDA formula with exceptional gains and losses; debt/cash definitions under each flag; ordering convention matches `dcf.py`.
- `redflags.py`:
  - **Clean auditor's report fixture (with standard boilerplate) → zero flags.**
  - One fixture per flag with the heading present.
  - CARO clauses with "has not defaulted" → no flag; "has defaulted" → flag; "Not applicable" → none.
  - Auditor-change detection across two periods.
- `verdict_in.py`: every row of the confidence table and each mode.
- `sector_router.py`: financial-sector text signals; override precedence.
- Numeric guard: narration with a number outside the computed set is rejected.

### 14.2 Integration / API tests
- `/api/aoc4/extract` with: XBRL-only bundle, PDF-only bundle, scanned PDF (OCR on and off), mixed years, wrong CIN, ambiguous units, unsupported file type, oversized upload.
- `/api/aoc4/analyze` for each scenario in §4.1, using a stub LLM so the test is deterministic.
- `/api/analyze` regression: US ticker response unchanged (snapshot test).

### 14.3 Golden / cross-check tests (need user-supplied data)
- For at least one **listed** company: extract from its AOC-4 and compare revenue, PAT, total assets against the same company's annual report / exchange XBRL and the yfinance figures. Tolerances: exact on XBRL totals, ≤ 0.5% on PDF.
- One XBRL filer, one non-XBRL PDF filer, one scanned filing.

### 14.4 Property tests
- `scale(x, unit)` then `unscale` round-trips; `parse_indian_number(format_inr(x)) == x` to the displayed precision.

---

## 15. Phased implementation plan

Each phase ends with passing tests and a short entry in `docs/decisions.md`.

### Phase 0: India foundation (§5)
**DoD:** Indian listed ticker analysis works end-to-end through `/api/analyze`, config guard works, US regression green.

### Phase 1: Bundle, classifier, models, validation framework, XBRL
Deliver: §6 models, `bundle.py`, `classifier.py`, `units.py`, `fiscal.py`, `numbers.py`, `xbrl_reader.py`, `validation.py` (V1–V4, V6–V12 that apply), `/api/aoc4/extract`, `scripts/dump_xbrl_concepts.py`.
**DoD:** with real XBRL samples, `extract` returns statements for ≥ 2 periods that pass V1; unit scaling resolved per OQ-1 and documented; security tests pass.

### Phase 2: PDF and OCR path
Deliver: `pdf_statements.py`, `label_map.py`, `ocr.py`, `merge.py`, V2/V3/V5/V9.
**DoD:** one non-XBRL and one scanned sample pass V1–V3; golden cross-check within tolerance; unmapped-row ratio reported.

### Phase 3: Valuation modes
Deliver: `to_dcf.py`, `sector_router.py`, `unlisted.py`, `verdict_in.py`, `AOC4Pipeline` stages 4–6 (without red flags), `/api/aoc4/analyze`.
**DoD:** scenarios B–G behave per §4.1 with a stubbed LLM; DCF refuses to run when `IN_*` unset; unlisted never returns BUY/SELL without a reference value.

### Phase 4: Sections, RAG, red flags, prompts, narration guard
Deliver: `sections.py`, `redflags.py`, India prompt variants, numeric guard.
**DoD:** clean-report fixture yields zero flags; every flagged item has quote, doc, page; narration guard test passes.

### Phase 5: Frontend (§12)
**DoD:** all scenarios usable from the UI; classification override and re-run work; null-safe rendering.

### Phase 6 (optional, separate spec)
Financial-sector valuation (P/B vs ROE-based justified multiple, residual income), AOC-2 related-party table parsing, MCA charges register input, quarterly-results TTM overlay for listed companies, async job queue for long OCR runs.

---

## 16. Open questions: resolve empirically, do not guess

Record each answer in `docs/aoc4_findings.md` with the sample file(s) used.

| ID | Question | How to resolve |
|----|----------|-----------------|
| OQ-1 | Are monetary values in MCA XBRL instances already in actual rupees, or in the declared "level of rounding" (lakhs/crores)? | Run `dump_xbrl_concepts.py` on ≥ 3 real instances; compare total assets with the PDF balance sheet's stated unit. Implement the scale step only after the answer is consistent across samples; keep V9 as a standing cross-check. |
| OQ-2 | What are the exact concept names (and namespaces) for each `Item`, for Ind AS and Indian GAAP taxonomies? | Build `xbrl_mapping.yaml` from the dump output. Handle both taxonomies. |
| OQ-3 | How are files named and split in real "View Public Documents" downloads, and is one PDF ever a merged multi-part document? | Inspect real downloads; tune the classifier (page-range splitting) accordingly. |
| OQ-4 | What does the current `find_peers()` do and does it return Indian names? | Read the code; implement `PeerUniverseProvider` accordingly. |
| OQ-5 | Ordering convention for `revenue_history`/`ebitda_history` and how `dcf.py` derives capex/NWC. | Read `dcf.py`; add tests pinning current behaviour before changing anything. |
| OQ-6 | Type of `red_flags` in `AnalyzeResponse`, and which consumers switch on `verdict`. | Grep the repo; adapt §6.1 accordingly. |
| OQ-7 | Does yfinance return consolidated or standalone figures for the Indian test tickers? | Compare against the annual report for 3–5 companies; record per-ticker findings. |
| OQ-8 | Current XBRL applicability thresholds for AOC-4. | Not needed for the code (the system reacts to whatever is uploaded). Do not hard-code any. |

---

## 17. Security, privacy, and legal notes

- **Data handling:** documents contain personal data (director names, DINs, signatures). Process in memory/temp directories, delete after the request, never log document text, and never send full documents to an LLM provider the user has not approved. Only the selected sections go to prompts.
- **Prompt injection:** treat filing text as hostile. Delimit it, instruct the model to ignore embedded instructions, and keep all tools read-only with no network or filesystem side effects.
- **Upload hardening:** §8.1 limits; run PDF/OCR parsing in a subprocess or worker with CPU/memory limits if the service is exposed beyond localhost.
- **MCA terms:** documents come from the user. Do not add scraping, captcha-solving, or automated purchasing of MCA documents. If bulk data is needed later, use a licensed data provider.
- **yfinance:** unofficial and subject to Yahoo's terms; fine for development, review before any commercial use.
- **Not investment advice:** the UI disclaimer must say so, and for unlisted outputs must state that the range depends on modelling assumptions, including the illiquidity discount.

---

## Appendix A: Schedule III label seeds (`label_map.py`)

Seed list: extend from real samples. Matching is case-insensitive after normalisation (strip punctuation and note references, collapse whitespace).

| `Item` | Division II (Ind AS) | Division I (Indian GAAP) |
|--------|----------------------|--------------------------|
| `total_assets` | Total assets | Total (right side / assets side of balance sheet) |
| `total_equity_and_liabilities` | Total equity and liabilities | Total (equity and liabilities side) |
| `total_equity` | Total equity | Total shareholders' funds |
| `equity_share_capital` | Equity share capital | Share capital |
| `other_equity` | Other equity | Reserves and surplus |
| `borrowings_non_current` | Borrowings (under non-current liabilities) | Long-term borrowings |
| `borrowings_current` | Borrowings (under current liabilities) | Short-term borrowings |
| `current_maturities_ltd` | Current maturities of long-term borrowings / debt | Current maturities of long-term debt |
| `lease_liabilities_*` | Lease liabilities | n/a |
| `trade_payables` | Trade payables | Trade payables |
| `trade_receivables` | Trade receivables | Trade receivables |
| `inventories` | Inventories | Inventories |
| `cash_and_equivalents` | Cash and cash equivalents | Cash and cash equivalents (or "Cash and bank balances") |
| `other_bank_balances` | Bank balances other than cash and cash equivalents | n/a |
| `current_investments` | Investments (under current assets) | Current investments |
| `revenue_from_operations` | Revenue from operations | Revenue from operations |
| `other_income` | Other income | Other income |
| `total_income` | Total income | Total revenue |
| `total_expenses` | Total expenses | Total expenses |
| `finance_costs` | Finance costs | Finance costs |
| `depreciation_amortisation` | Depreciation and amortisation expense | Depreciation and amortisation expense |
| `exceptional_items` | Exceptional items | Exceptional items |
| `profit_before_tax` | Profit/(loss) before tax | Profit/(loss) before tax |
| `current_tax` / `deferred_tax` | Current tax / Deferred tax | Current tax / Deferred tax |
| `tax_expense` | Total tax expense | Tax expense |
| `profit_after_tax` | Profit/(loss) for the year (period) | Profit/(loss) for the year |
| `cash_from_operations` | Net cash generated from / (used in) operating activities | same |
| `capex` | Purchase of property, plant and equipment (and intangible assets, CWIP) | Purchase of fixed assets (incl. CWIP, capital advances) |
| `closing_cash_per_cfs` | Cash and cash equivalents at the end of the year | same |
| `dividends_paid` | Dividend paid | same |

Add the synonyms actually seen in samples, such as "Net cash flow from operating activities", "Profit for the year", "Net profit after tax", "Purchase of fixed assets", "Rs." vs "₹" variants, and abbreviations ("PPE"). Totals rows with different wording ("Total", "TOTAL", "Total Assets") need position-aware handling (the final total on the asset side vs the equity-and-liabilities side).

## Appendix B: Definition of Done checklist (per phase)

- [ ] All new code typed; `ruff` and the type checker pass
- [ ] New tests written and passing; existing tests unchanged and passing
- [ ] US `/api/analyze` snapshot unchanged
- [ ] No new network calls in parsing paths
- [ ] No secrets or sample filings committed unless redistribution is permitted
- [ ] `docs/aoc4_findings.md` and `docs/decisions.md` updated
- [ ] Feature flags documented in `.env.example`
