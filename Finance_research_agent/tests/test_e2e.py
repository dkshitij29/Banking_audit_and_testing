"""End-to-end test: upload the test PDF, run the research pipeline, verify output."""
import asyncio, json, sys
from pathlib import Path
from agent.config import Settings
from agent.sec.parser import parse_filing
from agent.pipeline.research import ResearchPipeline
from agent.data.market_data import MarketDataProvider

PDF_PATH = Path(__file__).parent / "ACME_10K_2025.pdf"

async def main():
    if not PDF_PATH.exists():
        print("ERROR: Test PDF not found. Run: python tests/generate_test_filing.py")
        sys.exit(1)

    settings = Settings()
    print(f"Config: provider={settings.llm_provider}, model={settings.llm_model}")

    # Stage 1: Verify PDF parsing
    sections = parse_filing(str(PDF_PATH), "10-K")
    print(f"\n[STAGE 2 - PARSE] Sections extracted: {len(sections)}")
    for s in sections:
        print(f"  [{s.heading}] {len(s.text)} chars")

    # Stage 1+3+4+5: Run full pipeline with a REAL ticker (yfinance data)
    # We use AAPL because it has reliable market data. The PDF is just for
    # testing the upload/parse path; the valuation uses yfinance.
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    print(f"\n{'='*60}")
    print(f"Running full pipeline for {ticker}...")
    print(f"This takes ~30-90s depending on LLM speed.\n")

    pipeline = ResearchPipeline(settings)
    report = await pipeline.run(ticker, filing_paths=[str(PDF_PATH)])

    print(report.render())
    print(f"\n{'='*60}")
    print("VERDICT:", report.verdict.value)
    print("RATING: ", report.rating.value)
    print(f"FAIR VALUE: ${report.fair_value_mid:.0f} (range ${report.fair_value_low:.0f}-{report.fair_value_high:.0f})")
    print(f"UPSIDE:   {report.upside_pct:.1f}%")
    print(f"CURRENT:  ${report.current_price:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
