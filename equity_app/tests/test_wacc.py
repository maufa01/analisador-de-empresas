"""
analysis/wacc.py — beta regression, Hamada de/relevering, real cost of
debt, market capital structure, end-to-end WACC.

Beta tests use synthetic price series with a known β so we can assert
the regression recovers it. Real-world data tests use the AAPL fixture
for the cost-of-debt and tax-rate paths.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
import pytest

from analysis.wacc import (
    BetaResult, WACCResult,
    compute_beta, unlever_beta, relever_beta,
    capm_cost_of_equity, calculate_wacc,
    real_cost_of_debt, market_capital_structure,
    wacc_from_company,
)
from core.constants import DEFAULT_WACC_PARAMS
from core.exceptions import InsufficientDataError, ValuationError
from tests.fixtures import aapl_fy2023


# ============================================================
# Beta — synthetic recovery test
# ============================================================
class TestBetaRegression:

    def _synth_prices(self, beta: float, n_months: int = 60, seed: int = 42):
        """Generate price series where target_returns = beta * benchmark_returns + noise."""
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2018-01-31", periods=n_months, freq="ME")
        # Benchmark monthly log returns ~ N(0.008, 0.045) — realistic for S&P 500
        bench_r = rng.normal(loc=0.008, scale=0.045, size=n_months)
        noise = rng.normal(loc=0.0, scale=0.02, size=n_months)
        target_r = beta * bench_r + noise
        # Convert log returns to price levels starting at 100
        bench_price = 100 * np.exp(np.cumsum(bench_r))
        target_price = 100 * np.exp(np.cumsum(target_r))
        return (
            pd.Series(target_price, index=idx),
            pd.Series(bench_price, index=idx),
        )

    @pytest.mark.parametrize("true_beta", [0.7, 1.0, 1.3, 1.8])
    def test_recovers_known_beta(self, true_beta):
        target, bench = self._synth_prices(true_beta)
        result = compute_beta(target, bench)
        assert isinstance(result, BetaResult)
        # Allow ±0.15 — synthetic noise + monthly resampling drift
        assert result.beta == pytest.approx(true_beta, abs=0.15)

    def test_returns_metadata(self):
        target, bench = self._synth_prices(1.0)
        result = compute_beta(target, bench)
        assert result.n_observations >= 24
        assert 0.0 < result.r_squared <= 1.0
        assert result.method in ("statsmodels", "numpy")
        assert result.std_error > 0

    def test_insufficient_data_raises(self):
        idx = pd.date_range("2023-01-31", periods=10, freq="ME")
        s1 = pd.Series(np.linspace(100, 110, 10), index=idx)
        s2 = pd.Series(np.linspace(100, 105, 10), index=idx)
        with pytest.raises(InsufficientDataError):
            compute_beta(s1, s2)


# ============================================================
# Hamada de/relevering
# ============================================================
class TestHamada:

    def test_unlever_then_relever_roundtrip(self):
        # If target D/E equals current D/E, relever(unlever(β)) == β
        beta_l = 1.5
        de = 0.6
        tax = 0.25
        beta_u = unlever_beta(beta_l, de, tax)
        beta_back = relever_beta(beta_u, de, tax)
        assert beta_back == pytest.approx(beta_l, rel=1e-9)

    def test_unlever_reduces_beta_with_debt(self):
        # Adding debt levers up; removing debt unlevers down
        beta_l = 1.5
        beta_u = unlever_beta(beta_l, debt_to_equity=1.0, tax_rate=0.25)
        assert beta_u < beta_l

    def test_zero_debt_means_unlevered_equals_levered(self):
        assert unlever_beta(1.2, 0.0, 0.25) == 1.2
        assert relever_beta(1.2, 0.0, 0.25) == 1.2


# ============================================================
# CAPM + WACC math
# ============================================================
class TestWACCMath:

    def test_capm_cost_of_equity(self):
        # Re = 0.045 + 1.2 * 0.055 = 0.111
        re = capm_cost_of_equity(0.045, 1.2, 0.055)
        assert re == pytest.approx(0.111, rel=1e-9)

    def test_wacc_basic(self):
        result = calculate_wacc(
            risk_free=0.045,
            equity_risk_premium=0.055,
            beta=1.0,
            cost_of_debt_pretax=0.05,
            tax_rate=0.25,
            weight_equity=0.70,
            weight_debt=0.30,
        )
        # Re = 0.045 + 1.0 * 0.055 = 0.10
        # Rd_at = 0.05 * 0.75 = 0.0375
        # WACC = 0.7 * 0.10 + 0.3 * 0.0375 = 0.08125
        assert result.wacc == pytest.approx(0.08125, rel=1e-9)
        assert result.cost_of_equity == pytest.approx(0.10, rel=1e-9)
        assert result.cost_of_debt_after_tax == pytest.approx(0.0375, rel=1e-9)

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValuationError):
            calculate_wacc(
                risk_free=0.045, equity_risk_premium=0.055, beta=1.0,
                cost_of_debt_pretax=0.05, tax_rate=0.25,
                weight_equity=0.5, weight_debt=0.6,   # 1.10
            )

    def test_higher_beta_higher_wacc(self):
        kwargs = dict(
            risk_free=0.045, equity_risk_premium=0.055,
            cost_of_debt_pretax=0.05, tax_rate=0.25,
            weight_equity=0.7, weight_debt=0.3,
        )
        low = calculate_wacc(beta=0.8, **kwargs).wacc
        mid = calculate_wacc(beta=1.0, **kwargs).wacc
        high = calculate_wacc(beta=1.5, **kwargs).wacc
        assert low < mid < high


# ============================================================
# Cost of debt
# ============================================================
class TestCostOfDebt:

    def test_aapl_realistic(self):
        # AAPL interest expense ~3.9B over ~115B avg debt ≈ 3.4%
        rate = real_cost_of_debt(aapl_fy2023.income(), aapl_fy2023.balance())
        assert rate is not None
        assert 0.020 < rate < 0.060

    def test_returns_none_without_data(self):
        assert real_cost_of_debt(pd.DataFrame(), pd.DataFrame()) is None

    def test_clamps_unrealistic_high_rate(self):
        # Synthetic: tiny debt, huge interest -> would be 1000% rate
        idx = pd.to_datetime(["2022-12-31", "2023-12-31"])
        inc = pd.DataFrame({"interestExpense": [1_000_000_000, 1_000_000_000]}, index=idx)
        bal = pd.DataFrame({"totalDebt": [100_000, 100_000]}, index=idx)
        rate = real_cost_of_debt(inc, bal)
        assert rate is None or rate <= 0.20


# ============================================================
# Market capital structure
# ============================================================
class TestMarketCapStructure:

    def test_basic(self):
        we, wd = market_capital_structure(market_cap=700, total_debt=300)
        assert we == 0.7
        assert wd == 0.3

    def test_zero_total_raises(self):
        with pytest.raises(ValuationError):
            market_capital_structure(market_cap=0, total_debt=0)

    def test_all_equity(self):
        we, wd = market_capital_structure(market_cap=1000, total_debt=0)
        assert we == 1.0
        assert wd == 0.0


# ============================================================
# End-to-end
# ============================================================
class TestEndToEnd:

    def test_aapl_with_explicit_beta(self):
        result = wacc_from_company(
            income=aapl_fy2023.income(),
            balance=aapl_fy2023.balance(),
            market_cap=2_700_000_000_000,
            total_debt=111_088_000_000,
            beta_levered=1.20,
        )
        assert isinstance(result, WACCResult)
        # AAPL WACC should land in the 7-12% band — it has some debt but
        # its beta is moderate.
        assert 0.06 < result.wacc < 0.13

    def test_requires_either_beta_or_prices(self):
        with pytest.raises(InsufficientDataError):
            wacc_from_company(
                income=aapl_fy2023.income(),
                balance=aapl_fy2023.balance(),
                market_cap=1e12,
                total_debt=1e11,
            )
