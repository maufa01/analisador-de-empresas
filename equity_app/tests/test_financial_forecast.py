"""
analysis/financial_forecast.py — projection engine tests.
"""
from __future__ import annotations
import pandas as pd
import pytest

from analysis.financial_forecast import (
    ForecastInputs,
    _default_inputs_from_history,
    project_financials,
    project_bull_bear_base,
)


@pytest.fixture
def sample_financials():
    """7 years of mock financials with steady growth + steady margins."""
    periods = pd.date_range("2018", periods=7, freq="YE")
    income = pd.DataFrame({
        "revenue":         [100, 110, 121, 132, 145, 160, 175],
        "costOfRevenue":   [60,  66,  73,  80,  88,  97,  105],
        "grossProfit":     [40,  44,  48,  52,  57,  63,  70],
        "operatingIncome": [25,  28,  31,  35,  39,  44,  49],
        "ebit":            [25,  28,  31,  35,  39,  44,  49],
        "ebitda":          [30,  33,  37,  41,  46,  52,  58],
        "netIncome":       [17,  19.5, 22, 25, 28, 32, 36],
        "weightedAverageShsOut": [20]*7,
        "epsdiluted": [0.85, 0.97, 1.10, 1.25, 1.40, 1.60, 1.80],
        "incomeBeforeTax": [22, 25, 28, 32, 36, 41, 46],
        "incomeTaxExpense": [5, 5.5, 6, 7, 8, 9, 10],
    }, index=periods)
    balance = pd.DataFrame({
        "totalAssets":              [200, 220, 240, 260, 285, 310, 340],
        "totalDebt":                [60,  60,  55,  55,  50,  50,  45],
        "cashAndCashEquivalents":   [25,  30,  35,  40,  45,  50,  55],
        "totalStockholdersEquity":  [80,  90, 100, 110, 125, 140, 158],
        "totalCurrentLiabilities":  [40,  44,  48,  52,  57,  63,  70],
    }, index=periods)
    cash = pd.DataFrame({
        "operatingCashFlow":       [22, 24, 27, 30, 34, 38, 43],
        "capitalExpenditure":      [-10, -11, -12, -13, -14, -15, -17],
        "freeCashFlow":            [12, 13, 15, 17, 20, 23, 26],
        "stockBasedCompensation":  [2, 2.2, 2.5, 2.8, 3.1, 3.5, 3.9],
    }, index=periods)
    return income, balance, cash


class TestDefaultInputs:

    def test_growth_path_clamped_and_full_length(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        assert len(inp.revenue_growth_path) == 5
        # Historical CAGR ≈ 9.7% — within clamp range
        for g in inp.revenue_growth_path:
            assert -0.05 <= g <= 0.30

    def test_margin_paths_match_3y_avg(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        # 3y avg op margin: avg of 39/145, 44/160, 49/175 ≈ 27.4%
        assert 0.26 < inp.operating_margin_path[0] < 0.29
        # 3y avg net margin
        assert 0.19 < inp.net_margin_path[0] < 0.22

    def test_ocf_and_capex_default_from_history(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        assert inp.ocf_margin is not None
        assert 0.20 < inp.ocf_margin < 0.30
        assert inp.capex_pct_revenue is not None
        assert 0.05 < inp.capex_pct_revenue < 0.15


class TestProjectFinancials:

    def test_revenue_compounds_at_growth_rate(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        res = project_financials(income, balance, cash, inputs=inp, years=5)
        # First year revenue ≈ 175 × (1 + g1) ≈ 175 × 1.097 ≈ 192
        assert 188 < float(res.income_projected["revenue"].iloc[0]) < 195
        # Year 5 should be ~50% larger than year 1
        ratio = (res.income_projected["revenue"].iloc[-1]
                 / res.income_projected["revenue"].iloc[0])
        assert 1.4 < ratio < 1.5

    def test_net_income_consistent_with_margin(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        res = project_financials(income, balance, cash, inputs=inp, years=5)
        for idx in res.income_projected.index:
            ni = res.income_projected.loc[idx, "netIncome"]
            rev = res.income_projected.loc[idx, "revenue"]
            margin = ni / rev
            assert 0.19 < margin < 0.22

    def test_fcf_per_share_when_shares_provided(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        res = project_financials(income, balance, cash, inputs=inp,
                                  years=5, shares_outstanding=20_000_000)
        assert not res.fcf_per_share.empty
        # 5y total ≈ 167 / 20M ≈ $8.36 cumulative; per-yr ~ $1.30-2.0
        for v in res.fcf_per_share.values:
            assert v > 0


class TestScenarios:

    def test_bull_outperforms_base_outperforms_bear(self, sample_financials):
        income, balance, cash = sample_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        s = project_bull_bear_base(income, balance, cash, inp, years=5)
        bull_cum = s["bull"].cumulative_fcf.iloc[-1]
        base_cum = s["base"].cumulative_fcf.iloc[-1]
        bear_cum = s["bear"].cumulative_fcf.iloc[-1]
        assert bull_cum > base_cum > bear_cum
