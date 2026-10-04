import yfinance as yf
from datetime import datetime, date
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None

from agent.models.financials import IncomeStatement, BalanceSheet, CashFlow, PeriodBasis


class YFinanceAdapter:
    """Wrapper around yfinance for price, financials, and company info."""

    @staticmethod
    def fetch_price(ticker: str) -> Optional[dict]:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            fast_info = stock.fast_info

            price_data = {
                "ticker": ticker,
                "current_price": info.get("currentPrice") or fast_info.price,
                "previous_close": info.get("previousClose"),
                "open": info.get("open"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "beta": info.get("beta"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "trailing_eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
            }
            return price_data
        except Exception:
            return None

    @staticmethod
    def fetch_income_statement(ticker: str, years: int = 5) -> list[IncomeStatement]:
        results = []
        try:
            stock = yf.Ticker(ticker)
            is_data = stock.financials
            if is_data is None or is_data.empty:
                return results

            for col in is_data.columns[:years]:
                stmt = IncomeStatement(
                    period_end_date=col if isinstance(col, date) else col.date() if isinstance(col, datetime) else date.today(),
                    period=PeriodBasis.ANNUAL,
                    revenue=float(is_data.loc["Total Revenue", col]) if "Total Revenue" in is_data.index and col in is_data.columns else None,
                    gross_profit=float(is_data.loc["Gross Profit", col]) if "Gross Profit" in is_data.index and col in is_data.columns else None,
                    operating_income=float(is_data.loc["Operating Income", col]) if "Operating Income" in is_data.index and col in is_data.columns else None,
                    net_income=float(is_data.loc["Net Income", col]) if "Net Income" in is_data.index and col in is_data.columns else None,
                    ebitda=float(is_data.loc["EBITDA", col]) if "EBITDA" in is_data.index and col in is_data.columns else None,
                    depreciation_and_amortization=float(is_data.loc["Depreciation And Amortization", col]) if "Depreciation And Amortization" in is_data.index and col in is_data.columns else None,
                )
                if stmt.revenue:
                    results.append(stmt)
        except Exception:
            pass
        return results

    @staticmethod
    def fetch_balance_sheet(ticker: str, years: int = 5) -> list[BalanceSheet]:
        results = []
        try:
            stock = yf.Ticker(ticker)
            bs_data = stock.balance_sheet
            if bs_data is None or bs_data.empty:
                return results

            for col in bs_data.columns[:years]:
                bs = BalanceSheet(
                    period_end_date=col if isinstance(col, date) else col.date() if isinstance(col, datetime) else date.today(),
                    period=PeriodBasis.ANNUAL,
                    total_assets=float(bs_data.loc["Total Assets", col]) if "Total Assets" in bs_data.index else None,
                    total_current_assets=float(bs_data.loc["Total Current Assets", col]) if "Total Current Assets" in bs_data.index else None,
                    cash_and_equivalents=float(bs_data.loc["Cash And Cash Equivalents", col]) if "Cash And Cash Equivalents" in bs_data.index else None,
                    property_plant_equipment_net=float(bs_data.loc["Net PPE", col]) if "Net PPE" in bs_data.index else None,
                    goodwill=float(bs_data.loc["Goodwill", col]) if "Goodwill" in bs_data.index else None,
                    total_liabilities=float(bs_data.loc["Total Liabilities Net Minority Interest", col]) if "Total Liabilities Net Minority Interest" in bs_data.index else None,
                    total_current_liabilities=float(bs_data.loc["Total Current Liabilities", col]) if "Total Current Liabilities" in bs_data.index else None,
                    total_equity=float(bs_data.loc["Stockholders Equity", col]) if "Stockholders Equity" in bs_data.index else None,
                )
                if bs.total_assets:
                    results.append(bs)
        except Exception:
            pass
        return results

    @staticmethod
    def fetch_cash_flow(ticker: str, years: int = 5) -> list[CashFlow]:
        results = []
        try:
            stock = yf.Ticker(ticker)
            cf_data = stock.cashflow
            if cf_data is None or cf_data.empty:
                return results

            for col in cf_data.columns[:years]:
                cf = CashFlow(
                    period_end_date=col if isinstance(col, date) else col.date() if isinstance(col, datetime) else date.today(),
                    period=PeriodBasis.ANNUAL,
                    operating_cash_flow=float(cf_data.loc["Operating Cash Flow", col]) if "Operating Cash Flow" in cf_data.index else None,
                    capital_expenditure=float(cf_data.loc["Capital Expenditure", col]) if "Capital Expenditure" in cf_data.index else None,
                    free_cash_flow=float(cf_data.loc["Free Cash Flow", col]) if "Free Cash Flow" in cf_data.index else None,
                    depreciation_and_amortization=float(cf_data.loc["Depreciation And Amortization", col]) if "Depreciation And Amortization" in cf_data.index else None,
                )
                if cf.operating_cash_flow:
                    results.append(cf)
        except Exception:
            pass
        return results

    @staticmethod
    def fetch_company_info(ticker: str) -> Optional[dict]:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                "ticker": ticker,
                "company_name": info.get("shortName") or info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "employees": info.get("fullTimeEmployees"),
                "description": info.get("longBusinessSummary"),
                "beta": info.get("beta"),
                "website": info.get("website"),
            }
        except Exception:
            return None

    @staticmethod
    def fetch_historical_prices(ticker: str, period: str = "5y") -> Optional["pd.DataFrame"]:
        if pd is None:
            return None
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            return hist
        except Exception:
            return None
