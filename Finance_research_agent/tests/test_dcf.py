"""Tests for DCF calculation."""

import pytest
from agent.models.valuation import DCFInputs
from agent.valuation.dcf import calculate_dcf, _infer_growth_schedule, _get_latest


class TestGetLatest:
    def test_returns_last_valid(self):
        assert _get_latest([100, 200, 300]) == 300

    def test_skips_zeros(self):
        assert _get_latest([0, 200, 0]) == 200

    def test_empty_list(self):
        assert _get_latest([]) == 0.0

    def test_all_zeros(self):
        assert _get_latest([0, 0, 0]) == 0.0


class TestInferGrowthSchedule:
    def test_growing_revenue(self):
        schedule = _infer_growth_schedule([144, 120, 100], 10)
        assert len(schedule) == 10
        assert schedule[0] > 0

    def test_single_year_defaults(self):
        schedule = _infer_growth_schedule([100], 5)
        assert len(schedule) == 5
        assert all(s == 0.05 for s in schedule)

    def test_empty_defaults(self):
        schedule = _infer_growth_schedule([], 5)
        assert len(schedule) == 5


class TestDCFBasic:
    def _make_inputs(self, **kwargs) -> DCFInputs:
        defaults = {
            "ticker": "TEST",
            "shares_outstanding": 10_000_000,
            "tax_rate": 0.21,
            "revenue_history": [80e9, 100e9, 120e9],
            "ebitda_history": [20e9, 25e9, 30e9],
        }
        defaults.update(kwargs)
        return DCFInputs(**defaults)

    def test_positive_implied_price(self):
        inputs = self._make_inputs()
        result = calculate_dcf(inputs)
        assert result.implied_price > 0

    def test_no_revenue_history(self):
        inputs = self._make_inputs(revenue_history=[], ebitda_history=[])
        result = calculate_dcf(inputs)
        assert result.implied_price == 0
        assert any("No valid revenue" in w for w in result.warnings)

    def test_wacc_override(self):
        inputs = self._make_inputs()
        result = calculate_dcf(inputs, wacc_override=0.10)
        assert abs(result.wacc - 0.10) < 0.001

    def test_terminal_growth_capped(self):
        inputs = self._make_inputs()
        result = calculate_dcf(inputs, tg_override=0.15)
        assert result.terminal_growth_rate < result.wacc
        assert any("Terminal growth" in w for w in result.warnings)

    def test_sensible_wacc(self):
        inputs = self._make_inputs()
        result = calculate_dcf(inputs)
        assert 0.05 < result.wacc < 0.15

    def test_enterprise_value_positive(self):
        inputs = self._make_inputs()
        result = calculate_dcf(inputs)
        assert result.enterprise_value > 0
        assert result.pv_fcfs > 0
        assert result.terminal_value > 0
