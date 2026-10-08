"""Phase 3: Valuation bridge tests."""

import pytest
from decimal import Decimal
from datetime import date


class TestToDCF:
    def test_basic_conversion(self):
        from agent.aoc4.to_dcf import periods_to_dcf_inputs
        from agent.aoc4.models import PeriodStatements, Item

        periods = [
            PeriodStatements(
                period_end=date(2024, 3, 31),
                items={
                    Item.REVENUE_FROM_OPERATIONS: Decimal("100000"),
                    Item.PROFIT_BEFORE_TAX: Decimal("20000"),
                    Item.TAX_EXPENSE: Decimal("5000"),
                    Item.PROFIT_AFTER_TAX: Decimal("15000"),
                    Item.TOTAL_ASSETS: Decimal("500000"),
                    Item.TOTAL_EQUITY: Decimal("300000"),
                    Item.EQUITY_SHARE_CAPITAL: Decimal("10000"),
                },
            ),
            PeriodStatements(
                period_end=date(2025, 3, 31),
                items={
                    Item.REVENUE_FROM_OPERATIONS: Decimal("120000"),
                    Item.PROFIT_BEFORE_TAX: Decimal("25000"),
                    Item.TAX_EXPENSE: Decimal("6250"),
                    Item.PROFIT_AFTER_TAX: Decimal("18750"),
                    Item.TOTAL_ASSETS: Decimal("550000"),
                    Item.TOTAL_EQUITY: Decimal("320000"),
                    Item.EQUITY_SHARE_CAPITAL: Decimal("10000"),
                    Item.BORROWINGS_NON_CURRENT: Decimal("100000"),
                    Item.BORROWINGS_CURRENT: Decimal("50000"),
                    Item.CASH_AND_EQUIVALENTS: Decimal("30000"),
                },
            ),
        ]

        inputs = periods_to_dcf_inputs(periods, ticker="TEST.NS", shares_outstanding=1000000)

        assert inputs.ticker == "TEST.NS"
        assert inputs.shares_outstanding == 1000000
        assert len(inputs.revenue_history) == 2
        # Newest first
        assert inputs.revenue_history[0] == 120000
        assert inputs.net_debt == 100000 + 50000 - 30000  # 120000
        assert inputs.debt_ratio > 0

    def test_empty_periods_raises(self):
        from agent.aoc4.to_dcf import periods_to_dcf_inputs
        with pytest.raises(ValueError):
            periods_to_dcf_inputs([])

    def test_effective_tax_rate(self):
        from agent.aoc4.to_dcf import _estimate_effective_tax_rate
        from agent.aoc4.models import PeriodStatements, Item

        periods = [
            PeriodStatements(
                period_end=date(2025, 3, 31),
                items={
                    Item.PROFIT_BEFORE_TAX: Decimal("1000"),
                    Item.TAX_EXPENSE: Decimal("250"),
                },
            ),
        ]
        rate = _estimate_effective_tax_rate(periods)
        assert rate == 0.25


class TestSectorRouter:
    def test_detects_bank(self):
        from agent.valuation.sector_router import is_financial_sector
        assert is_financial_sector(sector="Financials") is True

    def test_detects_nbfc(self):
        from agent.valuation.sector_router import is_financial_sector
        assert is_financial_sector(
            description="Non-Banking Financial Company registered under RBI"
        ) is True

    def test_normal_company(self):
        from agent.valuation.sector_router import is_financial_sector
        assert is_financial_sector(sector="Technology", industry="Software") is False


class TestUnlisted:
    def test_unlever_relever(self):
        from agent.valuation.unlisted import unlever_beta, relever_beta
        beta_l = 1.2
        de = 0.5
        t = 0.25
        beta_u = unlever_beta(beta_l, de, t)
        beta_back = relever_beta(beta_u, de, t)
        assert abs(beta_back - beta_l) < 0.001

    def test_dlom(self):
        from agent.valuation.unlisted import apply_dlom
        result = apply_dlom(1000, 0.20)
        assert result == 800

    def test_cost_of_debt(self):
        from agent.valuation.unlisted import estimate_cost_of_debt
        rate = estimate_cost_of_debt(50, 1000, 0.07)
        assert 0.075 <= rate <= 0.19  # within bounds


class TestVerdictIn:
    def test_unsupported_sector(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode

        result = derive_verdict_in(None, None, None, None,
                                   ValuationMode.UNSUPPORTED_SECTOR, [], [])
        assert result.verdict == "INCONCLUSIVE"
        assert result.rating == "N/A"

    def test_intrinsic_range(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode

        result = derive_verdict_in(100, 120, None, None,
                                   ValuationMode.INTRINSIC_RANGE, [], [])
        assert result.verdict == "NOT_APPLICABLE"
        assert result.rating == "N/A"

    def test_undervalued(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode

        result = derive_verdict_in(200, 220, 150, None,
                                   ValuationMode.MARKET_RELATIVE, [], [])
        assert result.verdict == "UNDERVALUED"
        assert result.rating == "BUY"

    def test_overvalued(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode

        result = derive_verdict_in(50, 60, 100, None,
                                   ValuationMode.MARKET_RELATIVE, [], [])
        assert result.verdict == "OVERVALUED"
        assert result.rating == "SELL"

    def test_method_divergence(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode

        # DCF says 100, comps says 300 — huge divergence
        result = derive_verdict_in(100, 300, 150, None,
                                   ValuationMode.MARKET_RELATIVE, [], [])
        assert result.verdict == "INCONCLUSIVE"

    def test_distressed(self):
        from agent.valuation.verdict_in import derive_verdict_in
        from agent.aoc4.models import ValuationMode, RedFlag

        flags = [RedFlag(code="AUD_GOING_CONCERN", severity="high", title="Going concern", method="rule")]
        result = derive_verdict_in(100, 120, 150, None,
                                   ValuationMode.DISTRESSED, flags, [])
        assert result.verdict == "INCONCLUSIVE"


class TestRedFlags:
    def test_negative_net_worth(self):
        from agent.aoc4.redflags import detect_red_flags
        from agent.aoc4.models import PeriodStatements, Item

        periods = [
            PeriodStatements(
                period_end=date(2025, 3, 31),
                items={Item.TOTAL_EQUITY: Decimal("-1000")},
            ),
        ]
        flags = detect_red_flags({}, periods)
        codes = [f.code for f in flags]
        assert "NEGATIVE_NET_WORTH" in codes

    def test_loss_making_multi_year(self):
        from agent.aoc4.redflags import detect_red_flags
        from agent.aoc4.models import PeriodStatements, Item

        periods = [
            PeriodStatements(
                period_end=date(2024, 3, 31),
                items={Item.PROFIT_AFTER_TAX: Decimal("-500")},
            ),
            PeriodStatements(
                period_end=date(2025, 3, 31),
                items={Item.PROFIT_AFTER_TAX: Decimal("-800")},
            ),
        ]
        flags = detect_red_flags({}, periods)
        codes = [f.code for f in flags]
        assert "LOSS_MAKING_MULTI_YEAR" in codes

    def test_no_flags_clean_data(self):
        from agent.aoc4.redflags import detect_red_flags
        from agent.aoc4.models import PeriodStatements, Item

        periods = [
            PeriodStatements(
                period_end=date(2025, 3, 31),
                items={
                    Item.TOTAL_EQUITY: Decimal("50000"),
                    Item.PROFIT_AFTER_TAX: Decimal("10000"),
                    Item.CASH_FROM_OPERATIONS: Decimal("12000"),
                    Item.PROFIT_BEFORE_TAX: Decimal("15000"),
                    Item.FINANCE_COSTS: Decimal("1000"),
                },
            ),
        ]
        flags = detect_red_flags({}, periods)
        assert len(flags) == 0

    def test_auditor_qualified_opinion(self):
        from agent.aoc4.redflags import _auditor_opinion_flags
        text = "QUALIFIED OPINION\n\nWe have audited the accompanying financial statements..."
        flags = _auditor_opinion_flags(text, "d01")
        assert any(f.code == "AUD_QUALIFIED_OPINION" for f in flags)
