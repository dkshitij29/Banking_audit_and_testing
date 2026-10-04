"""FastAPI web server for the Finance Research Agent."""

import uuid
from pathlib import Path
from datetime import date
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from agent.config import Settings
from agent.models.api import (
    UploadFilingResponse,
    ResearchRequest,
    ResearchResponse,
    DCFRequest,
    CompsRequest,
    HealthResponse,
    FilingSummary,
)
from agent.pipeline.research import ResearchPipeline
from agent.sec.parser import parse_filing, create_filing_metadata
from agent.valuation.dcf import calculate_dcf, calculate_sensitivity
from agent.valuation.multiples import compute_comps
from agent.valuation.peer_screen import find_peers
from agent.models.valuation import DCFInputs
from agent.data.market_data import MarketDataProvider
import tempfile
import os


app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    app.state.pipeline = ResearchPipeline(settings)
    app.state.market_data = MarketDataProvider(settings)
    app.state.filings: dict = {}

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    yield

    pass


app = FastAPI(
    title="Finance Research Agent",
    description="Standalone investment research agent with SEC filing analysis and deterministic valuation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> HealthResponse:
    settings: Settings = app.state.settings
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider.value,
        providers={
            "market_data": "yfinance",
        },
    )


@app.post("/api/upload-filing")
async def upload_filing(
    file: UploadFile = File(...),
    ticker: str = Form(...),
    filing_type: Optional[str] = Form(None),
) -> UploadFilingResponse:
    settings: Settings = app.state.settings
    filings: dict = app.state.filings

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    upload_path = settings.upload_dir / f"{ticker}_{date.today().isoformat()}_{file.filename}"

    content = await file.read()
    with open(upload_path, "wb") as f:
        f.write(content)

    sections = parse_filing(str(upload_path), filing_type or "10-K")

    metadata = create_filing_metadata(
        ticker=ticker,
        filing_type=filing_type or "unknown",
        filing_path=str(upload_path),
    )

    for section in sections:
        section.filing_id = metadata.filing_id

    filings.setdefault(ticker, []).append({
        "metadata": metadata,
        "sections": sections,
        "path": str(upload_path),
    })

    return UploadFilingResponse(
        filing_id=metadata.filing_id,
        sections_extracted=len(sections),
        status="parsed",
    )


@app.post("/api/research")
async def run_research(request: ResearchRequest) -> ResearchResponse:
    pipeline: ResearchPipeline = app.state.pipeline
    filings: dict = app.state.filings

    filing_paths = []
    if request.filing_ids:
        ticker_filings = filings.get(request.ticker, [])
        for filing in ticker_filings:
            metadata = filing["metadata"]
            if metadata.filing_id in request.filing_ids:
                filing_paths.append(filing["path"])
    else:
        ticker_filings = filings.get(request.ticker, [])
        for filing in ticker_filings:
            filing_paths.append(filing["path"])

    try:
        report = await pipeline.run(request.ticker, filing_paths if filing_paths else None)
        report_id = str(uuid.uuid4())

        settings: Settings = app.state.settings
        output_path = settings.output_dir / f"{request.ticker}_{date.today().isoformat()}_{report_id}.txt"
        rendered = report.render()
        with open(output_path, "w") as f:
            f.write(rendered)

        return ResearchResponse(
            report=rendered,
            report_id=report_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")


@app.get("/api/filings/{ticker}")
async def list_filings(ticker: str) -> dict:
    filings: dict = app.state.filings
    ticker_filings = filings.get(ticker, [])

    summaries = []
    for filing in ticker_filings:
        metadata = filing["metadata"]
        summaries.append({
            "id": metadata.filing_id,
            "type": metadata.filing_type,
            "date": str(metadata.filing_date),
            "sections": len(filing["sections"]),
        })

    return {"ticker": ticker, "filings": summaries}


@app.post("/api/valuation/dcf")
async def run_dcf(request: DCFRequest) -> dict:
    market_data: MarketDataProvider = app.state.market_data
    price_data = market_data.fetch_price(request.ticker)

    if not price_data:
        raise HTTPException(status_code=404, detail=f"No price data for {request.ticker}")

    financials = market_data.fetch_financials(request.ticker)

    is_data = financials["income_statement"]
    revenues = [s.revenue for s in is_data if s.revenue and s.revenue > 0]
    ebitdas = [s.ebitda for s in is_data if s.ebitda and s.ebitda > 0]

    shares = price_data.get("shares_outstanding") or 0
    beta = price_data.get("beta") or 1.0

    inputs = DCFInputs(
        ticker=request.ticker,
        shares_outstanding=shares,
        tax_rate=0.21,
        beta=beta,
        revenue_history=revenues,
        ebitda_history=ebitdas,
        debt_ratio=0.3,
    )

    result = calculate_dcf(inputs, wacc_override=request.wacc, tg_override=request.terminal_growth)

    sensitivity = calculate_sensitivity(inputs)

    return {
        "ticker": request.ticker,
        "implied_price": result.implied_price,
        "enterprise_value": result.enterprise_value,
        "equity_value": result.equity_value,
        "wacc": result.wacc,
        "terminal_growth": result.terminal_growth_rate,
        "assumptions": result.assumptions,
        "warnings": result.warnings,
        "sensitivity": sensitivity,
    }


@app.post("/api/valuation/comps")
async def run_comps(request: CompsRequest) -> dict:
    market_data: MarketDataProvider = app.state.market_data

    if not request.peers:
        peers = find_peers(request.ticker, market_data)
    else:
        peers = request.peers

    result = compute_comps(request.ticker, peers, market_data)

    return {
        "ticker": request.ticker,
        "peers": [{"ticker": p.ticker, "ev_ebitda": p.ev_ebitda, "pe_ratio": p.pe_ratio} for p in result.peers],
        "median_ev_ebitda": result.median_ev_ebitda,
        "median_pe": result.median_pe,
        "implied_prices": {
            "ev_ebitda": result.implied_price_ev_ebitda,
            "pe": result.implied_price_pe,
            "median": result.implied_median_price,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
