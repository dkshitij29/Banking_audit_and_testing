"""Tests for WACC calculation."""

import pytest
from agent.valuation.wacc import calculate_wacc, adjust_beta_blume, estimate_debt_ratio, estimate_tax_rate


class TestBlumeAdjustment:
    def test_high_beta_reverts(self):
        result = adjust_beta_blume(1.5)
        assert 1.0 < result < 1.5

    def test_low_beta_unchanged(self):
        result = adjust_beta_blume(0.6)
        assert result == 0.6

    def test_unit_beta_unchanged(self):
        result = adjust_beta_blume(1.0)
        assert result == 1.0


class TestWACC:
    def test_default_params(self):
        cost_of_equity, wacc = calculate_wacc()
        assert cost_of_equity > 0
        assert wacc > 0
        assert wacc < cost_of_equity

    def test_higher_beta_higher_wacc(self):
        _, wacc_low = calculate_wacc(beta=0.8)
        _, wacc_high = calculate_wacc(beta=1.5)
        assert wacc_high > wacc_low

    def test_higher_debt_low_wacc(self):
        _, wacc_low = calculate_wacc(debt_ratio=0.1, cost_of_debt=0.04)
        _, wacc_high = calculate_wacc(debt_ratio=0.6, cost_of_debt=0.04)
        assert wacc_low > wacc_high

    def test_higher_tax_low_wacc(self):
        _, wacc_no_tax = calculate_wacc(tax_rate=0.0, debt_ratio=0.5)
        _, wacc_tax = calculate_wacc(tax_rate=0.3, debt_ratio=0.5)
        assert wacc_tax < wacc_no_tax


class TestDebtRatio:
    def test_equal_debt_equity(self):
        result = estimate_debt_ratio(100, 100)
        assert abs(result - 0.5) < 0.01

    def test_all_equity(self):
        result = estimate_debt_ratio(0, 100)
        assert result == 0.0

    def test_zero_capital(self):
        result = estimate_debt_ratio(0, 0)
        assert result == 0.3


class TestTaxRate:
    def test_normal(self):
        result = estimate_tax_rate(21, 100)
        assert abs(result - 0.21) < 0.01

    def test_zero_pretax(self):
        result = estimate_tax_rate(21, 0)
        assert result == 0.21

    def test_negative_clamped(self):
        result = estimate_tax_rate(-100, 100)
        assert result >= 0.0
        assert result <= 0.4
