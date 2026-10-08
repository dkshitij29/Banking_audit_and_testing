from typing import Optional
from agent.data.yfinance_adapter import YFinanceAdapter
from agent.models.financials import IncomeStatement, BalanceSheet, CashFlow
from agent.config import Settings
from agent.data.in_symbols import IndianSymbolResolver, AmbiguousSymbol
from agent.data.in_universe import IndiaStaticUniverse


class DataQualityError(Exception):
    """Raised when fetched data fails India validation."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class MarketDataProvider:
    """Unified market data interface with yfinance primary + optional FMP fallback.

    *market* controls ticker normalisation and validation:
    - ``"US"`` (default): US tickers, USD, no suffix.
    - ``"IN"``: Indian tickers → ``.NS``/``.BO`` suffix, INR validation.
    """

    def __init__(self, settings: Settings, market: str = "US"):
        self.settings = settings
        self.market = market.upper()
        self._yfinance = YFinanceAdapter()
        self._in_resolver = IndianSymbolResolver()
        self._in_universe = IndiaStaticUniverse()

    # ── Ticker normalisation ────────────────────────────────────────────────

    def normalize_ticker(self, raw: str) -> str:
        """Return a yfinance-compatible ticker for *raw*.

        For India, resolves via the symbol master (.NS/.BO).
        For US, passes through unchanged.
        """
        if self.market == "IN":
            result = self._in_resolver.resolve(raw)
            if isinstance(result, AmbiguousSymbol):
                raise DataQualityError(
                    "AMBIGUOUS_SYMBOL",
                    f"Multiple matches for {raw!r}: "
                    + ", ".join(c.ticker for c in result.candidates),
                )
            return result.ticker
        return raw.strip().upper()

    # ── Data fetching ───────────────────────────────────────────────────────

    def fetch_price(self, ticker: str) -> Optional[dict]:
        result = self._yfinance.fetch_price(ticker)
        if result and self.market == "IN":
            self._validate_in_price(result, ticker)
        return result

    def fetch_financials(self, ticker: str, years: int = 5) -> dict:
        return {
            "income_statement": self._yfinance.fetch_income_statement(ticker, years),
            "balance_sheet": self._yfinance.fetch_balance_sheet(ticker, years),
            "cash_flow": self._yfinance.fetch_cash_flow(ticker, years),
        }

    def fetch_company_info(self, ticker: str) -> Optional[dict]:
        return self._yfinance.fetch_company_info(ticker)

    # ── Peer discovery ──────────────────────────────────────────────────────

    def fetch_peers(self, ticker: str) -> list[str]:
        if self.market == "IN":
            return self._discover_in_peers(ticker)
        return self._discover_us_peers(ticker)

    def _discover_in_peers(self, ticker: str) -> list[str]:
        """Use the static India universe for peer discovery."""
        entry = self._in_universe.get_entry(ticker)
        sector = entry.sector if entry else None
        industry = entry.industry if entry else None

        # Fallback: try company info sector
        if not sector:
            info = self.fetch_company_info(ticker)
            if info:
                sector = info.get("sector")
                industry = info.get("industry")

        peers = self._in_universe.find_peers(ticker, sector=sector, industry=industry, n=5)
        return [p.symbol for p in peers]

    def _discover_us_peers(self, ticker: str) -> list[str]:
        """Original US peer discovery (unchanged)."""
        try:
            info = self.fetch_company_info(ticker)
            if info and info.get("sector"):
                sector = info["sector"]
                return self._discover_peers_by_sector(ticker, sector)
        except Exception:
            pass
        return []

    # ── India validation ────────────────────────────────────────────────────

    def _validate_in_price(self, data: dict, ticker: str):
        """Sanity-check price data for Indian tickers."""
        price = data.get("current_price")
        if price is None or price <= 0:
            raise DataQualityError("INVALID_PRICE", f"No valid price for {ticker}: {price}")
        shares = data.get("shares_outstanding")
        if shares is not None and shares <= 0:
            raise DataQualityError("INVALID_SHARES", f"Invalid shares outstanding for {ticker}: {shares}")

    # ── Beta computation ────────────────────────────────────────────────────

    def compute_beta(self, ticker: str, benchmark: str = "^NSEI", period: str = "3y") -> Optional[float]:
        """Compute beta from weekly returns vs *benchmark*.

        Requires ≥ 100 weekly observations. Returns ``None`` + warning if not.
        """
        try:
            import pandas as pd
        except ImportError:
            return None

        hist = self._yfinance.fetch_historical_prices(ticker, period)
        bench = self._yfinance.fetch_historical_prices(benchmark, period)

        if hist is None or bench is None or hist.empty or bench.empty:
            return None

        # Resample to weekly
        rets = hist["Close"].resample("W").last().pct_change()
        bench_rets = bench["Close"].resample("W").last().pct_change()

        # Align
        common = rets.align(bench_rets)[0].dropna()
        bench_aligned = rets.align(bench_rets)[1].dropna()

        n = len(common)
        if n < 100:
            return None  # too few observations

        cov = (common * bench_aligned).sum() / n
        bench_var = (bench_aligned ** 2).sum() / n

        if bench_var == 0:
            return None

        return cov / bench_var

    # ── Legacy US sector peers (unchanged) ──────────────────────────────────

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
