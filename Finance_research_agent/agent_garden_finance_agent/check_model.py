r"""Check that a model server can run the finance agent.

Checks the three things the agents need: plain chat, tool calling
(analysts) and structured output (the Portfolio Manager's final decision).
Run from the TradingAgents folder:
    .\.venv\Scripts\python ..\check_model.py
The server and model come from TradingAgents/.env (or TRADINGAGENTS_* variables).
Expected last line: ALL OK
"""
import sys
import time

from langchain_core.tools import tool

from tradingagents.default_config import DEFAULT_CONFIG as cfg
from tradingagents.llm_clients.factory import create_tier_client
from tradingagents.agents.structured import bind_structured
from tradingagents.agents.schemas import PortfolioDecision

print("backend:", cfg.get("backend_url"), "| model:", cfg.get("deep_think_llm"))
quick = create_tier_client(cfg, "quick").get_llm()
deep = create_tier_client(cfg, "deep").get_llm()
ok = True

t = time.time()
r = quick.invoke("In one sentence: what does an 'Underweight' stock rating mean?")
print(f"\n[1] plain chat ({time.time() - t:.1f}s):", str(r.content).strip()[:300])


@tool
def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Get daily OHLCV price data for a stock between two dates (yyyy-mm-dd)."""
    return "Date,Close\n2025-03-07,199.25\n2025-03-10,194.54"


t = time.time()
r = quick.bind_tools([get_stock_data]).invoke(
    "Fetch AMZN daily prices from 2025-02-10 to 2025-03-10 using the tool."
)
calls = getattr(r, "tool_calls", []) or []
print(f"\n[2] tool call ({time.time() - t:.1f}s):", calls if calls else f"NONE - text: {str(r.content)[:300]}")
ok &= bool(calls) and calls[0]["name"] == "get_stock_data"

t = time.time()
s = bind_structured(deep, PortfolioDecision, "smoke")
d = s.invoke(
    "You are the portfolio manager. The bull case: strong cloud growth. The bear case: "
    "tariff risk and a falling market. The risk team leans cautious. Give the final rating for AMZN."
) if s is not None else None
print(f"\n[3] structured decision ({time.time() - t:.1f}s):",
      f"rating={d.rating!s} | summary={d.executive_summary[:200]}" if d else "FAILED")
ok &= d is not None

print("\nALL OK" if ok else "\nPROBLEM")
sys.exit(0 if ok else 1)
