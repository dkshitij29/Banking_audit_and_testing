# Finance Research Agent

**Standalone investment research agent with SEC filing analysis and deterministic valuation.**

Upload SEC filings (10-K, 10-Q, 8-K), run the research pipeline, and get a structured investment report with DCF valuation, peer comps, bull/bear debate, and a Buy/Hold/Sell rating.

**Numbers computed by code. LLM only narrates.**

---

## Architecture

```
POST /api/research → 5-Stage Pipeline → ResearchReport

Stage 1 — INGEST        Fetch price + financials from yfinance
Stage 2 — PARSE          Parse SEC filings → sections (PDF/HTML)
Stage 3 — ANALYSE        Financial health agent + RAG QA over filings
Stage 4 — MODEL          Pure-Python DCF + comps + sensitivity matrix
Stage 5 — SYNTHESIZE     Bull/Bear/Judge debate → final report
```

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Numbers vs LLM | Numbers by code, LLM narrates | Deterministic, auditable outputs |
| Valuation | DCF + comps | Intrinsic + relative coverage |
| SEC parsing | pdfplumber + bs4 | Lightweight, no GPU needed |
| Retrieval | BM25 (rank-bm25) | Fast, deterministic, no vector DB |
| Framework | PydanticAI + FastAPI | Typed, async, tools-first |

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
# Edit .env — set OPENAI_API_KEY or ANTHROPIC_API_KEY + LLM_PROVIDER

# 4. Start the server
uvicorn agent.api.server:app --reload --port 8000
```

## API Endpoints

### `GET /api/health`
Health check. Returns LLM provider status.

### `POST /api/upload-filing`
Upload an SEC filing (PDF/HTML) for a ticker.

```bash
curl -X POST http://localhost:8000/api/upload-filing \
  -F "file=@AAPL_10K_2024.pdf" \
  -F "ticker=AAPL" \
  -F "filing_type=10-K"
```

**Response:**
```json
{
  "filing_id": "uuid-here",
  "sections_extracted": 15,
  "status": "parsed"
}
```

### `POST /api/research`
Run the full 5-stage research pipeline.

```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "filing_ids": ["uuid-here"]}'
```

**Response:**
```json
{
  "report": "Company: Apple Inc (AAPL) | Price: $228.87 | Date: 2026-09-29\nVerdict: ...\n...",
  "report_id": "uuid-here"
}
```

### `POST /api/valuation/dcf`
Run standalone DCF valuation.

```bash
curl -X POST http://localhost:8000/api/valuation/dcf \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "growth_rate": 0.08, "wacc": 0.10, "terminal_growth": 0.03}'
```

### `POST /api/valuation/comps`
Run standalone peer comparison.

```bash
curl -X POST http://localhost:8000/api/valuation/comps \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "peers": ["MSFT", "GOOGL", "META"]}'
```

### `GET /api/filings/{ticker}`
List uploaded filings for a ticker.

## Report Output Format

```
Company: Apple Inc (AAPL) | Price: $228.87 | Date: 2026-09-29
Verdict: Undervalued (fair value range $245–$290, midpoint $268, ~17% upside)
Derived rating: Buy (model-generated, confidence: Medium)

Why:
  • DCF implies $275/share vs current $229
  • Comps imply $262/share based on peer median multiples
  • Combined fair value midpoint: $268/share

Bull case:
  • [point 1]
  • [point 2]
  • [point 3]

Bear case:
  • [point 1]
  • [point 2]
  • [point 3]

Red flags:
  • [flag 1]
  • [flag 2]

Valuation detail — DCF: ...
Valuation detail — Comps: ...
Sensitivity (Growth × WACC): ...
Key assumptions: ...
What would change this view: ...
Sources: ...

Disclaimer: Research support, not financial advice
```

## Project Structure

```
finance_research_agent/
├── pyproject.toml              # Project dependencies
├── .env.example                # Configuration template
│
├── agent/
│   ├── config.py               # PydanticSettings from .env
│   │
│   ├── models/                 # Pydantic data models
│   │   ├── filing.py           # FilingMetadata, FilingSection
│   │   ├── financials.py       # IncomeStatement, BalanceSheet, CashFlow
│   │   ├── valuation.py        # DCFInputs, DCFResult, CompsData, SensitivityResult
│   │   ├── report.py           # ResearchReport
│   │   └── api.py              # Request/response schemas
│   │
│   ├── data/                   # Market data fetching
│   │   ├── yfinance_adapter.py # Price, financials, company info
│   │   └── market_data.py      # Unified interface + peer discovery
│   │
│   ├── sec/                    # SEC filing processing
│   │   ├── parser.py           # PDF/HTML → FilingSection
│   │   ├── retriever.py        # BM25 retrieval over filing text
│   │   └── qa.py               # RAG QA with section citations
│   │
│   ├── valuation/              # Deterministic compute (pure Python)
│   │   ├── wacc.py             # CAPM-based WACC
│   │   ├── dcf.py              # FCFF + projection + terminal value
│   │   ├── multiples.py        # EV/EBITDA, P/E, P/B peer comparison
│   │   ├── peer_screen.py      # Find peers by sector + market cap
│   │   ├── sensitivity.py      # 2D matrix (growth × WACC)
│   │   └── synthesis.py        # Weighted combination → fair value range
│   │
│   ├── agents/                 # PydanticAI agents
│   │   ├── tools.py            # Shared tools for all agents
│   │   ├── analysis.py         # Financial analysis agent
│   │   ├── valuation_agent.py  # Runs valuation, interprets assumptions
│   │   ├── debate.py           # Bull, Bear, Judge agents
│   │   └── orchestrator.py     # Lead agent, assembles report
│   │
│   ├── pipeline/               # Orchestrated workflow
│   │   ├── research.py         # 5-stage research pipeline
│   │   └── deps.py             # Dependency container
│   │
│   └── api/                    # FastAPI web server
│       └── server.py           # /upload-filing, /research, /health
│
├── upload/                     # Uploaded filings directory
├── output/                     # Generated reports
└── tests/                      # pytest suite (48 tests)
    ├── test_wacc.py
    ├── test_dcf.py
    ├── test_parser.py
    ├── test_retriever.py
    └── test_sensitivity.py
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: **48/48 passing**

## LLM Providers

Switch between OpenAI and Anthropic via `.env`:

| Provider | Environment |
|---|---|
| OpenAI | `LLM_PROVIDER=openai` + `OPENAI_API_KEY=sk-...` |
| Anthropic | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=sk-ant-...` |

Install the matching SDK:
```bash
uv pip install openai   # for OpenAI
uv pip install anthropic  # for Anthropic
```

## What's NOT in Scope

- No desktop/Tauri app — web API only
- No Monte Carlo simulation — sensitivity matrix suffices
- No earnings call transcript processing
- No LBO, SOTP, or residual income models
- No backtesting
- No real-time WebSocket streaming

## License

Part of the FinRobot project. See the repository root for license details.

## Disclaimer

**This project is for research support only. It does not constitute financial advice.**
