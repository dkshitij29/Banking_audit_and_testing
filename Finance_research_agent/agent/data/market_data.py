from typing import Optional
from agent.data.yfinance_adapter import YFinanceAdapter
from agent.models.financials import IncomeStatement, BalanceSheet, CashFlow
from agent.config import Settings


class MarketDataProvider:
    """Unified market data interface with yfinance primary + optional FMP fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._yfinance = YFinanceAdapter()

    def fetch_price(self, ticker: str) -> Optional[dict]:
        result = self._yfinance.fetch_price(ticker)
        if result:
            return result
        return None

    def fetch_financials(self, ticker: str, years: int = 5) -> dict:
        return {
            "income_statement": self._yfinance.fetch_income_statement(ticker, years),
            "balance_sheet": self._yfinance.fetch_balance_sheet(ticker, years),
            "cash_flow": self._yfinance.fetch_cash_flow(ticker, years),
        }

    def fetch_company_info(self, ticker: str) -> Optional[dict]:
        return self._yfinance.fetch_company_info(ticker)

    def fetch_peers(self, ticker: str) -> list[str]:
        try:
            info = self.fetch_company_info(ticker)
            if info and info.get("sector"):
                sector = info["sector"]
                return self._discover_peers_by_sector(ticker, sector)
        except Exception:
            pass
        return []

    def _discover_peers_by_sector(self, ticker: str, sector: str) -> list[str]:
        """Simple peer discovery: companies in the same sector by market cap."""
        known_sector_peers = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "AVGO", "ORCL", "CRM", "ADBE"],
            "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT"],
            "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP", "V", "MA"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD", "LOW", "SBUX"],
            "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "TMUS"],
            "Industrials": ["UNP", "HON", "UPS", "RTX", "BA", "CAT", "DE", "GE"],
            "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "PSX"],
            "Utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC"],
            "Real Estate": ["AMT", "PLD", "CCI", "EQIX", "PSA"],
            "Basic Materials": ["LIN", "APD", "ECL", "SHW", "NEM", "FCX"],
            "Consumer Defensive": ["WMT", "PG", "KO", "PEP", "COST", "PM", "MO"],
        }
        peers = known_sector_peers.get(sector, [])
        return [p for p in peers if p != ticker][:5]
