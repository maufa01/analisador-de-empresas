"""
analysis/earnings_quality.py — Beneish, Piotroski, Sloan tests.

We assert behavior on known-clean companies (AAPL, MSFT) and a financial
(JPM). The exact F-scores can shift slightly with the underlying data,
so we test ranges and flag-color, not point values for the score itself.

The Beneish M-Score IS asserted to be below the manipulator threshold
for AAPL/MSFT — that's the whole point of the test.
"""
from __future__ import annotations
import pandas as pd
import pytest

from analysis.earnings_quality import (
    QualityFlag, EarningsQuality,
    beneish_m_score, piotroski_f_score, sloan_ratio,
    assess_earnings_quality,
)
from core.constants import BENEISH_THRESHOLD, SLOAN_RED_FLAG
from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023


# ============================================================
# Beneish M-Score
# ============================================================
class TestBeneish:

    def test_aapl_clean(self):
        f = beneish_m_score(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert f is not None
        assert f.score < BENEISH_THRESHOLD
        assert f.flag == "green"
        # All 8 components present
        assert set(f.components) == {"DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"}

    def test_msft_clean(self):
        f = beneish_m_score(
            msft_fy2023.income(), msft_fy2023.balance(), msft_fy2023.cash_flow()
        )
        assert f is not None
        assert f.score < BENEISH_THRESHOLD

    def test_returns_none_without_history(self):
        # Only 1 year — Beneish needs t and t-1
        idx = pd.to_datetime(["2023-12-31"])
        inc = pd.DataFrame({"revenue": [100], "grossProfit": [40]}, index=idx)
        assert beneish_m_score(inc, pd.DataFrame(), pd.DataFrame()) is None


# ============================================================
# Piotroski F-Score
# ============================================================
class TestPiotroski:

    def test_aapl_strong(self):
        f = piotroski_f_score(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert f is not None
        # AAPL FY2023 lands at ~7/9 — strong
        assert f.score >= 6
        assert f.flag in ("green", "yellow")

    def test_score_bounded(self):
        for fix in (aapl_fy2023, msft_fy2023, jpm_fy2023):
            f = piotroski_f_score(fix.income(), fix.balance(), fix.cash_flow())
            assert f is not None
            assert 0 <= f.score <= 9

    def test_components_are_binary_and_sum_to_score(self):
        f = piotroski_f_score(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert all(v in (0, 1) for v in f.components.values())
        assert sum(f.components.values()) == int(f.score)


# ============================================================
# Sloan ratio
# ============================================================
class TestSloan:

    def test_aapl_clean(self):
        f = sloan_ratio(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert f is not None
        # AAPL accruals are very low — green
        assert abs(f.score) < SLOAN_RED_FLAG
        assert f.flag in ("green", "yellow")

    def test_high_accruals_flagged_red(self):
        # Synthetic: NI = 100, CFO = 0, TA = 500 -> Sloan = 0.20 (>0.10 threshold)
        idx = pd.to_datetime(["2022-12-31", "2023-12-31"])
        inc = pd.DataFrame({"netIncome": [50, 100]}, index=idx)
        bal = pd.DataFrame({"totalAssets": [400, 500]}, index=idx)
        cf = pd.DataFrame({"operatingCashFlow": [0, 0]}, index=idx)
        f = sloan_ratio(inc, bal, cf)
        assert f is not None
        assert f.flag == "red"
        assert f.score > SLOAN_RED_FLAG

    def test_returns_none_without_inputs(self):
        assert sloan_ratio(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()) is None


# ============================================================
# Aggregator
# ============================================================
class TestAssessment:

    def test_aapl_overall_green(self):
        eq = assess_earnings_quality(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert eq.overall_flag == "green"
        assert eq.beneish is not None
        assert eq.piotroski is not None
        assert eq.sloan is not None

    def test_overall_unknown_when_no_data(self):
        eq = assess_earnings_quality(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert eq.overall_flag == "unknown"

    def test_overall_takes_worst(self):
        # Build an EQ object directly with mixed flags
        eq = EarningsQuality(
            beneish=QualityFlag("Beneish M-Score", -2.0, "green", ""),
            piotroski=QualityFlag("Piotroski F-Score", 5, "yellow", ""),
            sloan=QualityFlag("Sloan Ratio", 0.02, "green", ""),
        )
        assert eq.overall_flag == "yellow"

    def test_red_dominates(self):
        eq = EarningsQuality(
            beneish=QualityFlag("B", -2.0, "green", ""),
            piotroski=QualityFlag("P", 8, "green", ""),
            sloan=QualityFlag("S", 0.20, "red", ""),
        )
        assert eq.overall_flag == "red"
