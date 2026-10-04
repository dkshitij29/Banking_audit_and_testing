"""Tests for sensitivity analysis."""

import pytest
from agent.models.valuation import DCFInputs
from agent.valuation.sensitivity import build_sensitivity_matrix, render_sensitivity_table
from agent.valuation.dcf import calculate_sensitivity


class TestSensitivityMatrix:
    def _make_inputs(self) -> DCFInputs:
        return DCFInputs(
            ticker="TEST",
            shares_outstanding=10_000_000,
            tax_rate=0.21,
            revenue_history=[80e9, 100e9, 120e9],
            ebitda_history=[20e9, 25e9, 30e9],
        )

    def test_matrix_shape(self):
        inputs = self._make_inputs()
        result = build_sensitivity_matrix(inputs, wacc_steps=3, growth_steps=4)
        assert len(result.wacc_values) == 3
        assert len(result.growth_values) == 4
        assert len(result.implied_prices) == 3
        for row in result.implied_prices:
            assert len(row) == 4

    def test_prices_positive(self):
        inputs = self._make_inputs()
        result = build_sensitivity_matrix(inputs)
        positive_count = sum(1 for row in result.implied_prices for p in row if p > 0)
        assert positive_count > 0

    def test_lower_wacc_higher_price(self):
        inputs = self._make_inputs()
        result = build_sensitivity_matrix(inputs, wacc_range=(0.07, 0.13), growth_range=(0.02, 0.03), wacc_steps=3, growth_steps=1)
        first_col = [result.implied_prices[i][0] for i in range(len(result.implied_prices)) if result.implied_prices[i][0] > 0]
        if len(first_col) >= 2:
            assert first_col[0] > first_col[-1]

    def test_render_table(self):
        inputs = self._make_inputs()
        result = build_sensitivity_matrix(inputs, wacc_steps=3, growth_steps=3)
        table = render_sensitivity_table(result)
        assert "SENSITIVITY ANALYSIS" in table
        assert "$" in table

    def test_base_price_recorded(self):
        inputs = self._make_inputs()
        result = build_sensitivity_matrix(inputs)
        assert result.base_price > 0
        assert result.base_wacc > 0
        assert result.base_growth > 0


class TestDCFSensitivity:
    def _make_inputs(self) -> DCFInputs:
        return DCFInputs(
            ticker="TEST",
            shares_outstanding=10_000_000,
            tax_rate=0.21,
            revenue_history=[80e9, 100e9, 120e9],
            ebitda_history=[20e9, 25e9, 30e9],
        )

    def test_returns_grid(self):
        inputs = self._make_inputs()
        result = calculate_sensitivity(inputs, wacc_steps=3, tg_steps=3)
        assert len(result["wacc_values"]) == 3
        assert len(result["growth_values"]) == 3
        assert len(result["implied_prices"]) == 3
        for row in result["implied_prices"]:
            assert len(row) == 3
        assert "base_wacc" in result
        assert "base_growth" in result
