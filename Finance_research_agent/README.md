# Finance Research Agent

**5-stage investment research pipeline with unified verdicts.**

Enter a ticker (optional SEC filing PDF) → run the pipeline → get a structured valuation verdict: **UNDERVALUED**, **OVERVALUED**, or **FAIRLY_VALUED** with full reasoning, bull/bear debate, and key assumptions.

**Numbers computed by code. LLM only narrates.**

---

## Architecture

```
POST /api/analyze → 5-Stage Pipeline → Verdict + Reasoning

Stage 1 — INGEST        Fetch price + financials from yfinance
Stage 2 — PARSE          Parse SEC filings → sections (PDF/HTML)
Stage 3 — ANALYSE        Financial health agent + RAG QA over filings
Stage 4 — MODEL          Pure-Python DCF + comps + sensitivity matrix
Stage 5 — SYNTHESIZE     Bull/Bear/Judge debate → final verdict
```

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Numbers vs LLM | Numbers by code, LLM narrates | Deterministic, auditable outputs |
| Valuation | DCF + comps | Intrinsic + relative coverage |
| SEC parsing | pdfplumber + bs4 | Lightweight, no GPU needed |
| Retrieval | BM25 (rank-bm25) | Fast, deterministic, no vector DB |
| Framework | PydanticAI + FastAPI | Typed, async, tools-first |
| Frontend | Single unified UI | One entry point, verdict card with collapsible sections |

## Quick Start

```bash
# 1. Clone and setup
cd Finance_research_agent
uv venv
source .venv/bin/activate

# 2. Install dependencies
uv pip install -e ".[dev,openai]"

# 3. Configure LLM provider
cp .env.example .env
# Edit .env — set your LLM provider:
#   OpenAI:  LLM_PROVIDER=openai + OPENAI_API_KEY=sk-...
#   Anthropic: LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY=sk-ant-...
#   vLLM:    LLM_PROVIDER=vllm + VLLM_BASE_URL=http://localhost:9000/v1

# 4. Start (backend + frontend)
bash start.sh
# → Backend: http://localhost:8000
# → Frontend: http://localhost:5173
```

## API Endpoints

### `GET /api/health`
Health check. Returns LLM provider status.

```bash
curl http://localhost:8000/api/health
```

### `POST /api/analyze`
**Single unified endpoint.** Runs the full 5-stage pipeline and returns a verdict.

With ticker only (market data):
```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "ticker=NVIDIA"
```

With ticker + SEC filing (PDF):
```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "ticker=NVDA" \
  -F "file=@nvidia_10k.pdf" \
  -F "filing_type=10-K"
```

**Response:**
```json
{
  "verdict": "OVERVALUED",
  "rating": "Sell",
  "reasoning": "Current price: $239.24\nDCF implied: $59/share\n...",
  "stages": [
    {"stage": "1. INGEST", "status": "complete", "summary": "Fetched market data..."},
    {"stage": "2. PARSE", "status": "complete", "summary": "Parsed 1 filing(s)"},
    {"stage": "3. ANALYSE", "status": "complete", "summary": "Financial health analysis..."},
    {"stage": "4. MODEL", "status": "complete", "summary": "DCF + peer comps valuation..."},
    {"stage": "5. SYNTHESIZE", "status": "complete", "summary": "Bull/bear debate..."}
  ],
  "valuation": {
    "fair_value_low": 49.86,
    "fair_value_high": 70.39,
    "fair_value_mid": 58.66,
    "current_price": 239.24,
    "upside_pct": -75.48,
    "confidence": "Low"
  },
  "bull_case": ["..."],
  "bear_case": ["..."],
  "red_flags": [],
  "dcf_assumptions": {...},
  "what_would_change": ["..."],
  "sources": ["SEC filing: nvidia_10k.pdf", "yfinance market data"]
}
```

## Verdicts

| Verdict | Rating | Condition |
|---|---|---|
| `UNDERVALUED` | Buy | Fair value > 15% above current price |
| `FAIRLY_VALUED` | Hold | Within ±15% of current price |
| `OVERVALUED` | Sell | Fair value > 15% below current price |

Confidence (High/Medium/Low) is derived from agreement between DCF and comps methods.

## Frontend

Single-page React app with:
- Ticker input + optional PDF upload
- 5-stage pipeline status display
- Verdict card (color-coded: green/red/blue)
- Collapsible sections: Reasoning, Stages, Bull Case, Bear Case, Red Flags, Key Assumptions, What Would Change View
- Sources + disclaimer

## Project Structure

```
finance_research_agent/
├── pyproject.toml              # Project dependencies
├── .env.example                # Configuration template
├── start.sh                    # One-command startup (backend + frontend)
│
├── agent/
│   ├── config.py               # PydanticSettings from .env
│   │
│   ├── models/                 # Pydantic data models
│   │   ├── filing.py           # FilingMetadata, FilingSection
│   │   ├── financials.py       # IncomeStatement, BalanceSheet, CashFlow
│   │   ├── valuation.py        # DCFInputs, DCFResult, CompsData, SensitivityResult
│   │   ├── report.py           # ResearchReport (Verdict, Rating enums)
│   │   └── api.py              # AnalyzeResponse, HealthResponse schemas
│   │
│   ├── data/                   # Market data fetching
│   │   ├── yfinance_adapter.py # Price, financials, company info from yfinance
│   │   └── market_data.py      # Unified interface + peer discovery
│   │
│   ├── sec/                    # SEC filing processing
│   │   ├── parser.py           # PDF/HTML → FilingSection
│   │   ├── retriever.py        # BM25 retrieval over filing text
│   │   └── qa.py               # RAG QA with section citations
│   │
│   ├── valuation/              # Deterministic compute (pure Python, no LLM)
│   │   ├── wacc.py             # CAPM-based WACC
│   │   ├── dcf.py              # FCFF + projection + terminal value
│   │   ├── multiples.py        # EV/EBITDA, P/E, P/B peer comparison
│   │   ├── peer_screen.py      # Find peers by sector + market cap
│   │   ├── sensitivity.py      # 2D matrix (growth × WACC)
│   │   └── synthesis.py        # Weighted DCF + comps → fair value range
│   │
│   ├── agents/                 # PydanticAI agents
│   │   ├── tools.py            # Shared tools for all agents
│   │   ├── analysis.py         # Financial analysis agent
│   │   └── debate.py           # Bull, Bear, Judge agents
│   │
│   ├── pipeline/               # Orchestrated workflow
│   │   ├── research.py         # 5-stage research pipeline
│   │   └── deps.py             # Dependency container
│   │
│   └── api/                    # FastAPI web server
│       └── server.py           # /api/health, /api/analyze
│
├── frontend/                   # React + Vite
│   ├── src/
│   │   ├── App.jsx             # Unified UI (ticker + verdict card)
│   │   ├── App.css             # Styles
│   │   └── main.jsx            # Entry point
│   └── package.json
│
├── upload/                     # Uploaded filings (runtime)
├── output/                     # Generated reports (runtime)
└── tests/                      # pytest suite
    ├── test_wacc.py
    ├── test_dcf.py
    ├── test_parser.py
    ├── test_retriever.py
    ├── test_sensitivity.py
    └── test_e2e.py
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## LLM Providers

Switch between providers via `.env`:

| Provider | Config |
|---|---|
| OpenAI | `LLM_PROVIDER=openai` + `OPENAI_API_KEY=sk-...` |
| Anthropic | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=sk-ant-...` |
| vLLM (local) | `LLM_PROVIDER=vllm` + `VLLM_BASE_URL=http://localhost:9000/v1` |

Install matching SDK:
```bash
uv pip install openai      # for OpenAI
uv pip install anthropic   # for Anthropic
# vLLM uses OpenAI-compatible SDK (already installed)
```

## What's NOT in Scope

- No Monte Carlo simulation — sensitivity matrix suffices
- No earnings call transcript processing
- No LBO, SOTP, or residual income models
- No backtesting
- No real-time WebSocket streaming

## License

Part of the FinRobot project. See the repository root for license details.

## Disclaimer

**This project is for research support only. It does not constitute financial advice.**
