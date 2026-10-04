"""Shared tools accessible to all PydanticAI agents."""

from pydantic_ai import RunContext
from agent.pipeline.deps import ResearchDeps
from agent.data.market_data import MarketDataProvider
from agent.valuation.dcf import calculate_dcf
from agent.valuation.multiples import compute_comps, render_comps_table
from agent.valuation.sensitivity import build_sensitivity_matrix, render_sensitivity_table
from agent.valuation.synthesis import combine_valuations
from agent.models.financials import IncomeStatement, BalanceSheet, CashFlow
from agent.sec.retriever import BM25Retriever
from agent.sec.qa import FilingQAIgent
from agent.config import Settings


def register_tools(agent):
    """Register shared tools on a PydanticAI agent."""

    @agent.tool
    async def get_current_price(ctx: RunContext[ResearchDeps], ticker: str) -> str:
        """Get current stock price and market data for a ticker."""
        data = ctx.deps.market_data.fetch_price(ticker)
        if not data:
            return f"Could not fetch price data for {ticker}"
        return (
            f"Price: ${data.get('current_price', 0):.2f}, "
            f"Market Cap: ${(data.get('market_cap') or 0)/1e9:.1f}B, "
            f"PE: {data.get('trailing_pe', 'N/A')}, "
            f"Beta: {data.get('beta', 'N/A')}, "
            f"Sector: {data.get('sector', 'N/A')}"
        )

    @agent.tool
    async def get_financial_summary(ctx: RunContext[ResearchDeps], ticker: str) -> str:
        """Get a summary of income statement, balance sheet, and cash flow."""
        financials = ctx.deps.market_data.fetch_financials(ticker)
        lines = [f"Financial Summary for {ticker}:"]

        is_data = financials["income_statement"]
        if is_data:
            latest = is_data[0]
            lines.append(f"\nIncome Statement (most recent):")
            lines.append(f"  Revenue: ${latest.revenue/1e9:.2f}B" if latest.revenue else "  Revenue: N/A")
            lines.append(f"  Gross Profit: ${latest.gross_profit/1e9:.2f}B" if latest.gross_profit else "  Gross Profit: N/A")
            lines.append(f"  Operating Income: ${latest.operating_income/1e9:.2f}B" if latest.operating_income else "  Operating Income: N/A")
            lines.append(f"  Net Income: ${latest.net_income/1e9:.2f}B" if latest.net_income else "  Net Income: N/A")
            lines.append(f"  EBITDA: ${latest.ebitda/1e9:.2f}B" if latest.ebitda else "  EBITDA: N/A")

        bs_data = financials["balance_sheet"]
        if bs_data:
            latest = bs_data[0]
            lines.append(f"\nBalance Sheet (most recent):")
            lines.append(f"  Total Assets: ${latest.total_assets/1e9:.2f}B" if latest.total_assets else "  Total Assets: N/A")
            lines.append(f"  Total Equity: ${latest.total_equity/1e9:.2f}B" if latest.total_equity else "  Total Equity: N/A")
            lines.append(f"  Total Liabilities: ${latest.total_liabilities/1e9:.2f}B" if latest.total_liabilities else "  Total Liabilities: N/A")

        cf_data = financials["cash_flow"]
        if cf_data:
            latest = cf_data[0]
            lines.append(f"\nCash Flow (most recent):")
            lines.append(f"  Operating CF: ${latest.operating_cash_flow/1e9:.2f}B" if latest.operating_cash_flow else "  Operating CF: N/A")
            lines.append(f"  Free CF: ${latest.free_cash_flow/1e9:.2f}B" if latest.free_cash_flow else "  Free CF: N/A")
            lines.append(f"  CapEx: ${latest.capital_expenditure/1e9:.2f}B" if latest.capital_expenditure else "  CapEx: N/A")

        return "\n".join(lines)

    @agent.tool
    async def query_filing(ctx: RunContext[ResearchDeps], question: str) -> str:
        """Query uploaded SEC filing text using semantic search."""
        if not ctx.deps.filing_section_retriever:
            return "No filing data uploaded for this ticker."

        qa = FilingQAIgent(ctx.deps.settings)
        answer = await qa.ask(ctx.deps.filing_section_retriever, question)
        return answer

    @agent.tool
    async def get_peer_info(ctx: RunContext[ResearchDeps], ticker: str) -> str:
        """Get competitor/peer tickers for a given ticker."""
        peers = ctx.deps.market_data.fetch_peers(ticker)
        if not peers:
            return f"Could not find peers for {ticker}"
        return f"Peers for {ticker}: {', '.join(peers)}"
