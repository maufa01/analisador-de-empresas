"""
analysis/ratios.py — unit, snapshot, and property-based tests.

Snapshot tests use the AAPL FY2023 fixture and assert each ratio matches
the value reported in the 10-K within 0.5% — i.e. the calculator does
arithmetic correctly given clean inputs. If any ratio drifts, the data
or the formula has changed.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
import pytest

from analysis.ratios import (
    ALIASES, _get, calculate_ratios,
    free_cash_flow, adjusted_fcf, maintenance_capex_estimate,
    cagr, yoy_growth,
    roe, roa, roic, effective_tax_rate,
    debt_to_equity, current_ratio, quick_ratio, interest_coverage,
    growth_summary,
)
from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023


REL = 5e-3   # 0.5% tolerance — accounting for rounding of inputs


# ============================================================
# Snapshot — AAPL FY2023 (10-K)
# ============================================================
class TestAAPLFY2023Snapshot:

    @pytest.fixture
    def stmts(self):
        return aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()

    @pytest.fixture
    def ratios(self, stmts):
        inc, bal, cf = stmts
        return calculate_ratios(inc, bal, cf)

    def test_revenue_value(self, ratios):
        assert ratios["Revenue"].iloc[-1] == pytest.approx(383_285_000_000, rel=REL)

    def test_gross_margin(self, ratios):
        # 169,148 / 383,285 = 44.13%
        assert ratios["Gross Margin %"].iloc[-1] == pytest.approx(44.13, rel=REL)

    def test_operating_margin(self, ratios):
        # 114,301 / 383,285 = 29.82%
        assert ratios["Operating Margin %"].iloc[-1] == pytest.approx(29.82, rel=REL)

    def test_ebitda_margin(self, ratios):
        # 129,564 / 383,285 = 33.80%
        assert ratios["EBITDA Margin %"].iloc[-1] == pytest.approx(33.80, rel=REL)

    def test_net_margin(self, ratios):
        # 96,995 / 383,285 = 25.31%
        assert ratios["Net Margin %"].iloc[-1] == pytest.approx(25.31, rel=REL)

    def test_roe_high(self, ratios):
        # 96,995 / 62,146 ≈ 156% — Apple's signature buyback-driven ROE
        assert ratios["ROE %"].iloc[-1] == pytest.approx(156.08, rel=REL)

    def test_roa(self, ratios):
        # 96,995 / 352,583 ≈ 27.51%
        assert ratios["ROA %"].iloc[-1] == pytest.approx(27.51, rel=REL)

    def test_debt_to_equity(self, ratios):
        # 111,088 / 62,146 ≈ 1.787
        assert ratios["Debt/Equity"].iloc[-1] == pytest.approx(1.787, rel=REL)

    def test_current_ratio(self, ratios):
        # 143,566 / 145,308 ≈ 0.988
        assert ratios["Current Ratio"].iloc[-1] == pytest.approx(0.988, rel=REL)

    def test_fcf_margin(self, ratios):
        # 99,584 / 383,285 ≈ 25.98%
        assert ratios["FCF Margin %"].iloc[-1] == pytest.approx(25.98, rel=REL)

    def test_fcf_adjusted_smaller_than_fcf(self, ratios):
        # FCF adj = FCF − SBC = 99,584 − 10,833 = 88,751
        assert ratios["FCF Adjusted (SBC)"].iloc[-1] == pytest.approx(88_751_000_000, rel=REL)
        assert ratios["FCF Adj Margin %"].iloc[-1] < ratios["FCF Margin %"].iloc[-1]

    def test_cash_conversion_close_to_one(self, ratios):
        # FCF / NI = 99,584 / 96,995 ≈ 1.027
        assert ratios["Cash Conversion"].iloc[-1] == pytest.approx(1.027, rel=REL)


# ============================================================
# free_cash_flow / adjusted_fcf
# ============================================================
class TestFCF:

    def test_aapl_fcf_uses_direct_field(self):
        cf = aapl_fy2023.cash_flow()
        fcf = free_cash_flow(cf)
        assert fcf.iloc[-1] == 99_584_000_000

    def test_aapl_fcf_adjusted_subtracts_sbc(self):
        cf = aapl_fy2023.cash_flow()
        adj = adjusted_fcf(cf)
        # 99,584M - 10,833M = 88,751M
        assert adj.iloc[-1] == 88_751_000_000

    def test_falls_back_to_ocf_plus_capex(self):
        # Strip out the freeCashFlow column to force the OCF + capex path
        cf = aapl_fy2023.cash_flow().drop(columns=["freeCashFlow"])
        fcf = free_cash_flow(cf)
        # 110,543M + (-10,959M) = 99,584M
        assert fcf.iloc[-1] == 99_584_000_000

    def test_returns_none_without_required_fields(self):
        cf = pd.DataFrame({"unrelated": [1, 2, 3]})
        assert free_cash_flow(cf) is None
        assert adjusted_fcf(cf) is None


# ============================================================
# CAGR / YoY
# ============================================================
class TestCAGR:

    def test_simple_doubling(self):
        idx = pd.date_range("2020", periods=4, freq="YE")
        s = pd.Series([100, 125.99, 158.74, 200.00], index=idx)
        # ~26% CAGR
        assert cagr(s) == pytest.approx(0.26, abs=0.005)

    def test_negative_start_returns_nan(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        s = pd.Series([-10, 5, 20], index=idx)
        assert math.isnan(cagr(s))

    def test_too_few_points_returns_nan(self):
        s = pd.Series([100.0])
        assert math.isnan(cagr(s))

    def test_periods_argument_uses_tail(self):
        # Series doubles each year: [1, 2, 4, 8, 16, 32]
        # 3-year CAGR requires 4 data points (t-3 .. t) -> tail(4) = [4, 8, 16, 32]
        # (32 / 4) ** (1/3) - 1 = 8 ** (1/3) - 1 = 1.0 = 100% YoY
        idx = pd.date_range("2018", periods=6, freq="YE")
        s = pd.Series([1, 2, 4, 8, 16, 32], index=idx)
        assert cagr(s, periods=3) == pytest.approx(1.0, abs=0.001)

    def test_yoy_growth_matches_pct_change(self):
        s = pd.Series([100.0, 110.0, 121.0])
        result = yoy_growth(s)
        assert result.iloc[1] == pytest.approx(0.10)
        assert result.iloc[2] == pytest.approx(0.10)


# ============================================================
# Effective tax rate
# ============================================================
class TestTaxRate:

    def test_aapl_tax_rate_in_realistic_range(self):
        inc = aapl_fy2023.income()
        # Apple effective tax rate is ~14-16%
        rate = effective_tax_rate(inc)
        assert 0.13 < rate < 0.18

    def test_falls_back_to_default_when_data_missing(self):
        empty = pd.DataFrame()
        assert effective_tax_rate(empty) == 0.25

    def test_clamps_negative(self):
        # Construct a fake df with negative pretax (would give negative rate)
        idx = pd.date_range("2020", periods=2, freq="YE")
        df = pd.DataFrame({
            "incomeTaxExpense": [100, 100],
            "ebit": [-1000, -1000],
        }, index=idx)
        # Should clamp to default 0.25
        assert effective_tax_rate(df) == 0.25


# ============================================================
# ROIC
# ============================================================
class TestROIC:

    def test_aapl_roic_high(self):
        inc = aapl_fy2023.income()
        bal = aapl_fy2023.balance()
        result = roic(inc, bal)
        assert result is not None
        # ROIC for AAPL is exceptionally high — call it >50%
        assert result.iloc[-1] > 0.50

    def test_returns_none_without_ebit(self):
        inc = pd.DataFrame()
        bal = aapl_fy2023.balance()
        assert roic(inc, bal) is None


# ============================================================
# Field aliasing — the resolver
# ============================================================
class TestAliases:

    def test_resolves_fmp_revenue_field(self):
        df = pd.DataFrame({"revenue": [100, 110, 120]})
        s = _get(df, "revenue")
        assert s is not None and list(s) == [100.0, 110.0, 120.0]

    def test_resolves_yfinance_revenue_alias(self):
        df = pd.DataFrame({"Total Revenue": [100, 110, 120]})
        s = _get(df, "revenue")
        assert s is not None and list(s) == [100.0, 110.0, 120.0]

    def test_returns_none_for_unknown_field(self):
        df = pd.DataFrame({"foo": [1, 2, 3]})
        assert _get(df, "revenue") is None

    def test_returns_none_for_empty_df(self):
        assert _get(pd.DataFrame(), "revenue") is None
        assert _get(None, "revenue") is None


# ============================================================
# Property-based — invariants
# ============================================================
class TestRatioInvariants:
    """Mathematical invariants that must hold regardless of input."""

    def test_gross_margin_le_100_pct(self):
        # Gross profit can't exceed revenue (cost of revenue >= 0)
        for fix in (aapl_fy2023, msft_fy2023):
            inc, bal, cf = fix.income(), fix.balance(), fix.cash_flow()
            r = calculate_ratios(inc, bal, cf)
            if "Gross Margin %" in r.columns:
                assert (r["Gross Margin %"].dropna() <= 100.0).all()

    def test_net_margin_le_gross_margin(self):
        for fix in (aapl_fy2023, msft_fy2023):
            inc, bal, cf = fix.income(), fix.balance(), fix.cash_flow()
            r = calculate_ratios(inc, bal, cf)
            if "Net Margin %" in r.columns and "Gross Margin %" in r.columns:
                last = r.iloc[-1]
                assert last["Net Margin %"] <= last["Gross Margin %"]

    def test_fcf_adjusted_le_fcf(self):
        # FCF − SBC ≤ FCF (SBC is positive)
        for fix in (aapl_fy2023, msft_fy2023):
            cf = fix.cash_flow()
            assert adjusted_fcf(cf).iloc[-1] <= free_cash_flow(cf).iloc[-1]

    def test_current_ratio_positive(self):
        for fix in (aapl_fy2023, msft_fy2023, jpm_fy2023):
            bal = fix.balance()
            cr = current_ratio(bal)
            if cr is not None:
                assert (cr.dropna() > 0).all()


# ============================================================
# Master aggregator
# ============================================================
class TestCalculateRatios:

    def test_returns_dataframe(self):
        inc, bal, cf = aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        r = calculate_ratios(inc, bal, cf)
        assert isinstance(r, pd.DataFrame)
        assert not r.empty

    def test_ratios_index_matches_input(self):
        inc = aapl_fy2023.income()
        r = calculate_ratios(inc, aapl_fy2023.balance(), aapl_fy2023.cash_flow())
        assert r.index.equals(inc.index)

    def test_does_not_crash_on_partial_data(self):
        # Only revenue, nothing else — should still return a (very thin) DF
        idx = pd.date_range("2020", periods=2, freq="YE")
        inc = pd.DataFrame({"revenue": [100.0, 110.0]}, index=idx)
        r = calculate_ratios(inc, pd.DataFrame(), pd.DataFrame())
        assert isinstance(r, pd.DataFrame)
        assert "Revenue" in r.columns

    def test_wacc_arg_adds_roic_minus_wacc(self):
        inc = aapl_fy2023.income()
        bal = aapl_fy2023.balance()
        cf = aapl_fy2023.cash_flow()
        r = calculate_ratios(inc, bal, cf, wacc=0.08)
        assert "ROIC - WACC (pp)" in r.columns
        assert r["ROIC - WACC (pp)"].iloc[-1] > 0  # AAPL creates value


# ============================================================
# Growth summary
# ============================================================
def test_growth_summary_returns_dict():
    inc = aapl_fy2023.income()
    cf = aapl_fy2023.cash_flow()
    summary = growth_summary(inc, cf)
    assert "revenue" in summary
    assert "cagr_3y" in summary["revenue"]


# ============================================================
# Bug regressions
# ============================================================
def test_effective_tax_rate_uses_pretax_not_ebit():
    """Bug regression: must use incomeBeforeTax, not EBIT.

    For a company with $30M of interest expense, EBIT = $130, pretax = $100.
    Tax of $21 against the right denominator gives ~21% (true rate).
    Against the wrong denominator (EBIT) it gives ~16% — too low, which
    inflates NOPAT and ROIC silently.
    """
    income = pd.DataFrame({
        "ebit":             [130, 140, 150],
        "incomeBeforeTax":  [100, 110, 120],   # interest expense = 30
        "incomeTaxExpense": [21,  23,  25],
    }, index=pd.date_range("2022", periods=3, freq="YE"))

    rate = effective_tax_rate(income, periods=3)
    assert 0.19 < rate < 0.23, f"Got {rate}, expected ~0.21"


def test_effective_tax_rate_falls_back_to_ebit_when_pretax_missing(caplog):
    """When pretax_income isn't available, fall back to EBIT but log."""
    import logging
    income = pd.DataFrame({
        "ebit":             [100, 110, 120],
        "incomeTaxExpense": [21,  23,  25],
    }, index=pd.date_range("2022", periods=3, freq="YE"))

    with caplog.at_level(logging.WARNING):
        rate = effective_tax_rate(income, periods=3)

    assert 0.18 < rate < 0.22
    assert any("ebit_fallback" in rec.message for rec in caplog.records)
