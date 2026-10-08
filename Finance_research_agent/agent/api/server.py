"""FastAPI server — single unified analysis endpoint."""

from datetime import date
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

from agent.config import Settings
from agent.config.markets import is_india_config_ready
from agent.models.api import (
    AnalyzeResponse,
    HealthResponse,
    StageResult,
    ValuationMetrics,
)
from agent.pipeline.research import ResearchPipeline
from agent.api import aoc4_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings
    app.state.pipeline = ResearchPipeline(settings)
    app.state.aoc4_pipeline_ready = True
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Finance Research Agent",
    description="5-stage research pipeline with valuation verdicts.",
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

# Include AOC-4 routes
app.include_router(aoc4_routes.router)


@app.get("/api/health")
async def health() -> HealthResponse:
    settings: Settings = app.state.settings
    india = is_india_config_ready(
        settings.in_risk_free_rate,
        settings.in_equity_risk_premium,
    )
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider.value,
        providers={
            "market_data": "yfinance",
            "india_config_ready": india["ready"],
            "ocr_available": settings.ocr_enabled,
        },
    )


@app.post("/api/analyze")
async def run_analyze(
    ticker: str = Form(...),
    file: Optional[UploadFile] = File(None),
    filing_type: Optional[str] = Form(None),
) -> AnalyzeResponse:
    """Unified endpoint: ticker + optional PDF → 5-stage analysis → verdict."""
    pipeline: ResearchPipeline = app.state.pipeline
    settings: Settings = app.state.settings

    filing_paths = []

    if file and file.filename:
        upload_path = settings.upload_dir / f"{ticker}_{date.today().isoformat()}_{file.filename}"
        content = await file.read()
        with open(upload_path, "wb") as f:
            f.write(content)
        filing_paths.append(str(upload_path))

    try:
        report = await pipeline.run(ticker, filing_paths or None)

        stages = [
            StageResult(stage="1. INGEST", status="complete",
                        summary=f"Fetched market data and financials for {ticker}"),
            StageResult(stage="2. PARSE",
                        status="complete" if filing_paths else "skipped",
                        summary=f"Parsed {len(filing_paths)} filing(s)" if filing_paths
                                else "No filing uploaded — using market data only"),
            StageResult(stage="3. ANALYSE", status="complete",
                        summary="Financial health analysis completed"),
            StageResult(stage="4. MODEL", status="complete",
                        summary="DCF + peer comps valuation completed"),
            StageResult(stage="5. SYNTHESIZE", status="complete",
                        summary="Bull/bear debate + final verdict rendered"),
        ]

        reasoning_parts = [
            f"Current price: ${report.current_price:.2f}",
            f"DCF implied price: ${report.fair_value_mid:.0f}/share",
            f"Fair value range: ${report.fair_value_low:.0f} – ${report.fair_value_high:.0f}",
            f"Confidence: {report.confidence}",
            "",
            "Valuation basis:",
        ]
        for w in report.why:
            reasoning_parts.append(f"  - {w}")
        reasoning_parts += ["", "Bull arguments:"]
        for b in report.bull_case[:3]:
            reasoning_parts.append(f"  - {b}")
        reasoning_parts += ["", "Bear arguments:"]
        for b in report.bear_case[:3]:
            reasoning_parts.append(f"  - {b}")
        if report.red_flags:
            reasoning_parts += ["", "Red flags:"]
            for r in report.red_flags[:3]:
                reasoning_parts.append(f"  - {r}")

        verdict_label = report.verdict.value.upper().replace(" ", "_")

        return AnalyzeResponse(
            verdict=verdict_label,
            rating=report.rating.value,
            reasoning="\n".join(reasoning_parts),
            stages=stages,
            valuation=ValuationMetrics(
                fair_value_low=report.fair_value_low,
                fair_value_high=report.fair_value_high,
                fair_value_mid=report.fair_value_mid,
                current_price=report.current_price,
                upside_pct=report.upside_pct,
                confidence=report.confidence,
            ),
            bull_case=report.bull_case,
            bear_case=report.bear_case,
            red_flags=report.red_flags,
            dcf_assumptions=report.key_assumptions,
            what_would_change=report.what_would_change_view,
            sources=report.sources,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
