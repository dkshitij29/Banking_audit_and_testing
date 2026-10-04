"""Quick curl tests for the Finance Research Agent pipeline."""

echo "
============================================================
  FINANCE RESEARCH AGENT - API TEST COMMANDS
============================================================

Prerequisites: Backend running on port 8000
  Start with: ./start.sh

------------------------------------------------------------
TEST 1: Upload the test PDF (ACME 10-K)
------------------------------------------------------------
curl -X POST http://localhost:8000/api/upload-filing \\
  -F 'file=@tests/ACME_10K_2025.pdf' \\
  -F 'ticker=AAPL' \\
  -F 'filing_type=10-K'

Expected: {\\\"filing_id\\\": \\\"uuid...\\\", \\\"sections_extracted\\\": 16, \\\"status\\\": \\\"parsed\\\"}
Copy the filing_id for step 3.

------------------------------------------------------------
TEST 2: List uploaded filings for a ticker
------------------------------------------------------------
curl http://localhost:8000/api/filings/AAPL

Expected: {\\\"ticker\\\": \\\"AAPL\\\", \\\"filings\\\": [{\\\"id\\\": \\\"uuid...\\\", \\\"type\\\": \\\"10-K\\\", \\\"sections\\\": 16}]}

------------------------------------------------------------
TEST 3: Run full research pipeline (takes 30-90s)
------------------------------------------------------------
curl -X POST http://localhost:8000/api/research \\
  -H 'Content-Type: application/json' \\
  -d '{\\\"ticker\\\": \\\"AAPL\\\", \\\"filing_ids\\\": [\\\"<paste_filing_id_here>\\\"]}'

Expected: A full research report with DCF, comps, bull/bear debate, verdict.

------------------------------------------------------------
TEST 4: Standalone DCF valuation (no filing needed)
------------------------------------------------------------
curl -X POST http://localhost:8000/api/valuation/dcf \\
  -H 'Content-Type: application/json' \\
  -d '{\\\"ticker\\\": \\\"AAPL\\\", \\\"growth_rate\\\": 0.08, \\\"wacc\\\": 0.10, \\\"terminal_growth\\\": 0.03}'

Expected: DCF implied price, enterprise value, WACC, sensitivity matrix.

------------------------------------------------------------
TEST 5: Standalone peer comparison
------------------------------------------------------------
curl -X POST http://localhost:8000/api/valuation/comps \\
  -H 'Content-Type: application/json' \\
  -d '{\\\"ticker\\\": \\\"AAPL\\\", \\\"peers\\\": [\\\"MSFT\\\", \\\"GOOGL\\\", \\\"META\\\"]}'

Expected: Peer multiples (EV/EBITDA, P/E), implied fair value.

------------------------------------------------------------
TEST 6: Health check
------------------------------------------------------------
curl http://localhost:8000/api/health

Expected: {\\\"status\\\": \\\"ok\\\", \\\"llm_provider\\\": \\\"vllm\\\", \\\"providers\\\": {\\\"market_data\\\": \\\"yfinance\\\"}}

------------------------------------------------------------
E2E SCRIPT (runs pipeline in-process, no curl needed)
------------------------------------------------------------
PYDANTIC_AI_NO_BANNER=1 .venv/bin/python tests/test_e2e.py AAPL

Runs Stages 1-5 against your vLLM endpoint. Takes 30-90s.

============================================================
"
