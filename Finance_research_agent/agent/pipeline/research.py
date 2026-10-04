"""5-Stage Research Pipeline: Ingest → Parse → Analyse → Model → Synthesize."""

import uuid
from datetime import date
from typing import Optional
from pathlib import Path

from agent.config import Settings
from agent.pipeline.deps import ResearchDeps
from agent.data.market_data import MarketDataProvider
from agent.sec.parser import parse_filing
from agent.sec.retriever import BM25Retriever
from agent.sec.qa import FilingQAIgent
from agent.valuation.wacc import calculate_wacc, estimate_debt_ratio, estimate_tax_rate
from agent.valuation.dcf import calculate_dcf
from agent.valuation.multiples import compute_comps, render_comps_table
from agent.valuation.peer_screen import find_peers
from agent.valuation.sensitivity import build_sensitivity_matrix, render_sensitivity_table
from agent.valuation.synthesis import combine_valuations
from agent.models.valuation import DCFInputs
from agent.models.financials import IncomeStatement, BalanceSheet, CashFlow
from agent.models.report import ResearchReport, Verdict, Rating
from agent.agents.analysis import create_analysis_agent
from agent.agents.debate import create_bull_agent, create_bear_agent, create_judge_agent


class ResearchPipeline:
    """Orchestrates the 5-stage research pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.market_data = MarketDataProvider(settings)

    async def run(self, ticker: str, filing_paths: list[str] = None) -> ResearchReport:
        """Execute full 5-stage pipeline and return ResearchReport."""
        deps = ResearchDeps(
            settings=self.settings,
            market_data=self.market_data,
        )

        # Stage 1: INGEST — Fetch market data
        price_data = self.market_data.fetch_price(ticker)
        financials = self.market_data.fetch_financials(ticker)
        company_info = self.market_data.fetch_company_info(ticker)

        if not price_data:
            raise ValueError(f"Could not fetch price data for {ticker}")

        current_price = price_data.get("current_price", 0)
        company_name = company_info.get("company_name", ticker) if company_info else ticker
        deps.company_name = company_name

        # Stage 2: PARSE — Parse SEC filings
        if filing_paths:
            all_sections = []
            for path in filing_paths:
                sections = parse_filing(path)
                all_sections.extend(sections)
            deps.filing_sections = all_sections
            deps.filing_section_retriever = BM25Retriever.build_index(all_sections)

        # Stage 3: ANALYSE — Financial analysis agent
        analysis_agent = create_analysis_agent(self.settings)
        qa_agent = FilingQAIgent(self.settings)

        analysis_prompt = f"Analyze the financial health of {company_name} ({ticker})."
        try:
            analysis_result = await analysis_agent.run(analysis_prompt, deps=deps)
            analysis_text = analysis_result.output
        except Exception:
            analysis_text = "Financial analysis could not be completed."

        risk_text = ""
        red_flags_from_filing: list[str] = []
        if deps.filing_section_retriever:
            try:
                risk_text = await qa_agent.ask(deps.filing_section_retriever, "What are the top risks facing this company?")
                sources_text = await qa_agent.ask(deps.filing_section_retriever, "What are the key risk factors?")
            except Exception:
                risk_text = "Risk analysis from filings unavailable."

        # Stage 4: MODEL — Deterministic valuation (pure Python, no LLM)
        dcf_result = self._run_dcf(ticker, price_data, financials)
        comps_result = self._run_comps(ticker)
        sensitivity_result = self._run_sensitivity(ticker, price_data, financials)
        combined = combine_valuations(dcf_result, comps_result)

        # Stage 5: SYNTHESIZE — Debate + orchestrator
        return await self._synthesize(
            ticker=ticker,
            company_name=company_name,
            current_price=current_price,
            analysis_text=analysis_text,
            risk_text=risk_text,
            red_flags=red_flags_from_filing,
            dcf_result=dcf_result,
            comps_result=comps_result,
            sensitivity_result=sensitivity_result,
            combined=combined,
            filing_paths=filing_paths,
        )

    def _run_dcf(self, ticker: str, price_data: dict, financials: dict) -> "DCFResult":
        is_data = financials["income_statement"]
        bs_data = financials["balance_sheet"]
        cf_data = financials["cash_flow"]

        latest_is = is_data[0] if is_data else None
        latest_bs = bs_data[0] if bs_data else None
        latest_cf = cf_data[0] if cf_data else None

        revenues = [s.revenue for s in is_data if s.revenue and s.revenue > 0]
        ebitdas = [s.ebitda for s in is_data if s.ebitda and s.ebitda > 0]

        total_debt = 0
        equity = 0
        cash = 0
        if latest_bs:
            short_debt = latest_bs.short_term_debt or 0
            long_debt = latest_bs.long_term_debt or 0
            total_debt = short_debt + long_debt
            equity = latest_bs.total_equity or 0
            cash = latest_bs.cash_and_equivalents or 0

        net_debt = total_debt - cash
        debt_ratio = total_debt / (total_debt + equity) if (total_debt + equity) > 0 else 0.3

        tax_rate = 0.21
        if latest_is and latest_is.pretax_income and latest_is.income_tax_expense:
            tax_rate = estimate_tax_rate(latest_is.income_tax_expense, latest_is.pretax_income)

        shares = price_data.get("shares_outstanding") or (latest_is.shares_outstanding if latest_is else None) or 0
        beta = price_data.get("beta") or 1.0

        inputs = DCFInputs(
            ticker=ticker,
            shares_outstanding=shares,
            tax_rate=tax_rate,
            beta=beta,
            debt_ratio=debt_ratio,
            revenue_history=revenues,
            ebitda_history=ebitdas,
            net_debt=net_debt,
            short_term_debt=bs_data[0].short_term_debt if bs_data and bs_data[0].short_term_debt else 0,
            long_term_debt=bs_data[0].long_term_debt if bs_data and bs_data[0].long_term_debt else 0,
            cash_and_equivalents=cash,
        )

        return calculate_dcf(inputs)

    def _run_comps(self, ticker: str):
        peers = find_peers(ticker, self.market_data)
        if not peers:
            peers = self.market_data.fetch_peers(ticker)
        return compute_comps(ticker, peers, self.market_data)

    def _run_sensitivity(self, ticker: str, price_data: dict, financials: dict):
        is_data = financials["income_statement"]
        bs_data = financials["balance_sheet"]

        latest_bs = bs_data[0] if bs_data else None
        total_debt = 0
        equity = 0
        if latest_bs:
            total_debt = (latest_bs.short_term_debt or 0) + (latest_bs.long_term_debt or 0)
            equity = latest_bs.total_equity or 0

        net_debt = total_debt - (latest_bs.cash_and_equivalents or 0 if latest_bs else 0)

        revenues = [s.revenue for s in is_data if s.revenue and s.revenue > 0]
        ebitdas = [s.ebitda for s in is_data if s.ebitda and s.ebitda > 0]

        shares = price_data.get("shares_outstanding") or 0
        beta = price_data.get("beta") or 1.0

        inputs = DCFInputs(
            ticker=ticker,
            shares_outstanding=shares,
            tax_rate=0.21,
            beta=beta,
            debt_ratio=total_debt / (total_debt + equity) if (total_debt + equity) > 0 else 0.3,
            revenue_history=revenues,
            ebitda_history=ebitdas,
            net_debt=net_debt,
        )

        return build_sensitivity_matrix(inputs)

    async def _synthesize(
        self,
        ticker: str,
        company_name: str,
        current_price: float,
        analysis_text: str,
        risk_text: str,
        red_flags: list[str],
        dcf_result,
        comps_result,
        sensitivity_result,
        combined: dict,
        filing_paths: list[str] = None,
    ) -> ResearchReport:
        """Stage 5: Debate + orchestrator → final report."""
        bull_agent = create_bull_agent(self.settings)
        bear_agent = create_bear_agent(self.settings)
        judge_agent = create_judge_agent(self.settings)

        context_for_debate = f"""
        Company: {company_name} ({ticker})
        Current Price: ${current_price:.2f}

        Financial Analysis:
        {analysis_text}

        Valuation Results:
        DCF Implied Price: ${combined.get('dcf_price', 0):.2f}
        Comps Implied Price: ${combined.get('comps_price', 0):.2f}
        Combined Fair Value: ${combined.get('fair_value_mid', 0):.2f}
        Range: ${combined.get('fair_value_low', 0):.0f} – ${combined.get('fair_value_high', 0):.0f}
        Confidence: {combined.get('confidence', 'Low')}

        Risk Assessment:
        {risk_text}
        """

        bull_response = ""
        bear_response = ""
        judge_response = ""

        try:
            deps_tmp = ResearchDeps(
                settings=self.settings,
                market_data=self.market_data,
            )
            bull_result = await bull_agent.run(f"Analyze {company_name} ({ticker}). Make the bull case.\n\n{context_for_debate}", deps=deps_tmp)
            bull_response = bull_result.output
        except Exception:
            bull_response = "Bull case analysis unavailable."

        try:
            bear_result = await bear_agent.run(f"Analyze {company_name} ({ticker}). Make the bear case.\n\n{context_for_debate}", deps=deps_tmp)
            bear_response = bear_result.output
        except Exception:
            bear_response = "Bear case analysis unavailable."

        try:
            judge_prompt = f"""
            Evaluate the following bull and bear cases for {company_name} ({ticker}):

            Bull Case:
            {bull_response}

            Bear Case:
            {bear_response}

            Valuation: DCF=${combined.get('dcf_price', 0):.0f}, Comps=${combined.get('comps_price', 0):.0f},
            Combined=${combined.get('fair_value_mid', 0):.0f} ({combined.get('confidence', 'Low')} confidence)
            Current Price: ${current_price:.2f}

            Render your verdict.
            """
            judge_result = await judge_agent.run(judge_prompt, deps=deps_tmp)
            judge_response = judge_result.output
        except Exception:
            judge_response = "Judge verdict unavailable."

        verdict, rating, confidence_str = self._derive_verdict(combined, current_price)

        why = [
            f"DCF implies ${combined.get('dcf_price', 0):.0f}/share vs current ${current_price:.0f}",
            f"Comps imply ${combined.get('comps_price', 0):.0f}/share based on peer median multiples",
            f"Combined fair value midpoint: ${combined.get('fair_value_mid', 0):.0f}/share",
        ]

        bull_points = self._extract_points(bull_response, max_n=3)
        bear_points = self._extract_points(bear_response, max_n=3)

        comps_table = render_comps_table(comps_result)
        sensitivity_table = render_sensitivity_table(sensitivity_result)

        dcf_range = f"DCF implied: ${dcf_result.implied_price:.0f}/share (WACC: {dcf_result.wacc:.1%}, Terminal growth: {dcf_result.terminal_growth_rate:.1%})"

        sources = []
        if filing_paths:
            for p in filing_paths:
                sources.append(f"SEC filing: {Path(p).name}")
        sources.append("yfinance market data")

        key_assumptions = dcf_result.assumptions.copy()

        what_would_change = [
            "Significant change in revenue growth trajectory",
            "Margin expansion or compression >2 percentage points",
            "Material change in interest rates impacting WACC",
        ]

        upside = ((combined.get("fair_value_mid", 0) - current_price) / current_price * 100) if current_price > 0 else 0

        return ResearchReport(
            company=company_name,
            ticker=ticker,
            current_price=current_price,
            report_date=date.today(),
            verdict=verdict,
            fair_value_low=combined.get("fair_value_low", 0),
            fair_value_high=combined.get("fair_value_high", 0),
            fair_value_mid=combined.get("fair_value_mid", 0),
            upside_pct=upside,
            rating=rating,
            confidence=confidence_str,
            why=why,
            bull_case=bull_points,
            bear_case=bear_points,
            red_flags=red_flags,
            dcf_range=dcf_range,
            comps_table=comps_table,
            sensitivity_table=sensitivity_table,
            key_assumptions=key_assumptions,
            what_would_change_view=what_would_change,
            sources=sources,
        )

    @staticmethod
    def _derive_verdict(combined: dict, current_price: float) -> tuple[Verdict, Rating, str]:
        mid = combined.get("fair_value_mid", 0)
        confidence = combined.get("confidence", "Low")

        if current_price <= 0 or mid <= 0:
            return Verdict.FAIRLY_VALUED, Rating.HOLD, confidence

        upside = (mid - current_price) / current_price

        if upside > 0.15:
            return Verdict.UNDERVALUED, Rating.BUY, confidence
        elif upside < -0.15:
            return Verdict.OVERVALUED, Rating.SELL, confidence
        else:
            return Verdict.FAIRLY_VALUED, Rating.HOLD, confidence

    @staticmethod
    def _extract_points(text: str, max_n: int = 3) -> list[str]:
        lines = text.strip().split("\n")
        points = []
        for line in lines:
            stripped = line.strip()
            if stripped and (stripped[0].isdigit() and "." in stripped[:4] or stripped.startswith("•") or stripped.startswith("-")):
                points.append(stripped.lstrip("0123456789.-• ").strip())
            if len(points) >= max_n:
                break
        if not points:
            sentences = text.split(".")
            for s in sentences:
                s = s.strip()
                if len(s) > 20:
                    points.append(s + ".")
                if len(points) >= max_n:
                    break
        return points[:max_n]
