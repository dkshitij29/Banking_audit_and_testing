from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from enum import Enum


class PeriodBasis(str, Enum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class IncomeStatement(BaseModel):
    period_end_date: date
    period: PeriodBasis = PeriodBasis.ANNUAL
    revenue: float
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_expense: Optional[float] = None
    operating_income: Optional[float] = None
    interest_expense: Optional[float] = None
    pretax_income: Optional[float] = None
    income_tax_expense: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    depreciation_and_amortization: Optional[float] = None
    shares_outstanding: Optional[float] = None
    eps: Optional[float] = None
    eps_diluted: Optional[float] = None


class BalanceSheet(BaseModel):
    period_end_date: date
    period: PeriodBasis = PeriodBasis.ANNUAL
    total_assets: Optional[float] = None
    total_current_assets: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    accounts_receivable: Optional[float] = None
    inventory: Optional[float] = None
    property_plant_equipment_net: Optional[float] = None
    goodwill: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_current_liabilities: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    accounts_payable: Optional[float] = None
    total_equity: Optional[float] = None
    retained_earnings: Optional[float] = None
    shares_outstanding: Optional[float] = None


class CashFlow(BaseModel):
    period_end_date: date
    period: PeriodBasis = PeriodBasis.ANNUAL
    operating_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    free_cash_flow: Optional[float] = None
    dividends_paid: Optional[float] = None
    stock_based_compensation: Optional[float] = None
    depreciation_and_amortization: Optional[float] = None
    change_in_working_capital: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    investing_cash_flow: Optional[float] = None
