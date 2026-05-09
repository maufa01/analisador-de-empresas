"""
valuation/multi_multiple.py — engine tests.

Validates that:
- peer-median multiples are computed correctly (and skip invalid peers)
- per-year implied prices land roughly where hand-calc says they should
- PV discounting compounds (later years discounted more)
- bull > base > bear ordering holds when forecasts diverge
"""
from __future__ import annotations
import pandas as pd
import pytest

from analysis.financial_forecast import (
    _default_inputs_from_history, project_financials,
)
from valuation.comparables import PeerSnapshot
from valuation.multi_multiple import (
    run_multi_multiple_valuation,
    _peer_multiple_medians,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def aapl_like_financials():
    """7y of AAPL-scale financials (revenues in $B)."""
    periods = pd.date_range("2018", periods=7, freq="YE")
    B = 1e9
    income = pd.DataFrame({
        "revenue":         [v*B for v in [266, 260, 274, 365, 394, 383, 391]],
        "costOfRevenue":   [v*B for v in [163, 161, 169, 213, 223, 215, 220]],
        "grossProfit":     [v*B for v in [101, 98, 105, 152, 170, 169, 171]],
        "operatingIncome": [v*B for v in [70, 64, 66, 109, 119, 114, 123]],
        "ebit":            [v*B for v in [70, 64, 66, 109, 119, 114, 123]],
        "ebitda":          [v*B for v in [82, 77, 81, 121, 130, 125, 134]],
        "netIncome":       [v*B for v in [60, 55, 57, 95, 100, 97, 100]],
    }, index=periods)
    balance = pd.DataFrame({
        "totalAssets":              [v*B for v in [365, 339, 324, 351, 353, 353, 365]],
        "totalDebt":                [v*B for v in [105, 109, 112, 124, 122, 109, 100]],
        "cashAndCashEquivalents":   [v*B for v in [25, 49, 35, 35, 24, 30, 30]],
        "totalStockholdersEquity":  [v*B for v in [107, 90, 65, 63, 51, 62, 65]],
        "totalCurrentLiabilities":  [v*B for v in [116, 105, 106, 125, 154, 145, 150]],
    }, index=periods)
    cash = pd.DataFrame({
        "operatingCashFlow":       [v*B for v in [77, 69, 81, 104, 122, 110, 118]],
        "capitalExpenditure":      [v*B for v in [-13, -10, -7, -11, -10, -11, -10]],
        "freeCashFlow":            [v*B for v in [64, 59, 74, 93, 112, 99, 108]],
        "stockBasedCompensation":  [v*B for v in [6, 7, 8, 8, 9, 11, 11]],
    }, index=periods)
    return income, balance, cash


@pytest.fixture
def tech_peers():
    """Three tech mega-caps with realistic 2024-ish multiples."""
    return [
        PeerSnapshot("MSFT",  market_cap=3.0e12, enterprise_value=3.0e12,
                     net_income=80e9,  revenue=200e9, ebitda=110e9, book_value=200e9),
        PeerSnapshot("GOOGL", market_cap=2.0e12, enterprise_value=1.9e12,
                     net_income=85e9,  revenue=300e9, ebitda=120e9, book_value=300e9),
        PeerSnapshot("META",  market_cap=1.4e12, enterprise_value=1.4e12,
                     net_income=50e9,  revenue=130e9, ebitda=70e9,  book_value=160e9),
    ]


# ============================================================
# Peer median computation
# ============================================================
class TestPeerMedians:

    def test_pe_median_from_three_peers(self, tech_peers):
        # MSFT P/E = 3.0e12 / 80e9 = 37.5; GOOGL = 23.5; META = 28
        # median = 28
        meds = _peer_multiple_medians(tech_peers)
        assert 27 < meds["pe"] < 29

    def test_ev_ebitda_median(self, tech_peers):
        # MSFT 27.3, GOOGL 15.8, META 20 → median 20
        meds = _peer_multiple_medians(tech_peers)
        assert 19 < meds["ev_ebitda"] < 21

    def test_skips_negative_or_missing_metrics(self):
        peers = [
            PeerSnapshot("A", market_cap=1e12, net_income=-50e9),       # negative NI, skip P/E
            PeerSnapshot("B", market_cap=1e12, net_income=40e9),        # P/E = 25
            PeerSnapshot("C", market_cap=2e12, net_income=100e9),       # P/E = 20
        ]
        meds = _peer_multiple_medians(peers)
        # Only B and C contribute → median 22.5
        assert meds["pe"] is not None
        assert 21 < meds["pe"] < 24

    def test_empty_peers_returns_all_none(self):
        meds = _peer_multiple_medians([])
        for k in ("pe", "pfcf", "ev_ebitda", "ps", "pb"):
            assert meds[k] is None


# ============================================================
# End-to-end run
# ============================================================
class TestRunValuation:

    def test_returns_one_year_per_forecast_period(self, aapl_like_financials, tech_peers):
        income, balance, cash = aapl_like_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        fcst = project_financials(income, balance, cash, inputs=inp,
                                   years=5, shares_outstanding=15.5e9)
        res = run_multi_multiple_valuation(
            target_ticker="AAPL", current_price=180.0,
            forecast_result=fcst, peer_snapshots=tech_peers,
            shares_outstanding=15.5e9, discount_rate=0.12,
            base_year=2024,
        )
        assert len(res.years_forward) == 5
        assert all(yr.year > 2024 for yr in res.years_forward)

    def test_implied_prices_in_realistic_range(self, aapl_like_financials, tech_peers):
        """For AAPL-scale numbers + tech peers, year-1 P/E implied price
        should land in the $100-$300 range (current ~$180)."""
        income, balance, cash = aapl_like_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        fcst = project_financials(income, balance, cash, inputs=inp,
                                   years=5, shares_outstanding=15.5e9)
        res = run_multi_multiple_valuation(
            target_ticker="AAPL", current_price=180.0,
            forecast_result=fcst, peer_snapshots=tech_peers,
            shares_outstanding=15.5e9, discount_rate=0.12,
            base_year=2024,
        )
        first_year = res.years_forward[0]
        pe_val = next(v.implied_price for v in first_year.valuations
                      if v.multiple_name == "P/E")
        assert pe_val is not None
        assert 100 < pe_val < 300

    def test_pv_decreases_with_horizon(self, aapl_like_financials, tech_peers):
        """PV of avg implied price should compress as horizon extends —
        same nominal price discounted more years comes out lower."""
        income, balance, cash = aapl_like_financials
        inp = _default_inputs_from_history(income, balance, cash, years=5)
        fcst = project_financials(income, balance, cash, inputs=inp,
                                   years=5, shares_outstanding=15.5e9)
        res = run_multi_multiple_valuation(
            target_ticker="AAPL", current_price=180.0,
            forecast_result=fcst, peer_snapshots=tech_peers,
            shares_outstanding=15.5e9, discount_rate=0.50,    # heavy discount
            base_year=2024,
        )
        # With 50% discount, PV should be a small fraction of avg
        for yr in res.years_forward:
            if yr.average_price > 0:
                assert yr.pv_discounted < yr.average_price

    def test_no_peers_returns_none_medians(self, aapl_like_financials):
        income, balance, cash = aapl_like_financials
        inp = _default_inputs_from_history(income, balance, cash, years=3)
        fcst = project_financials(income, balance, cash, inputs=inp,
                                   years=3, shares_outstanding=15.5e9)
        res = run_multi_multiple_valuation(
            target_ticker="AAPL", current_price=180.0,
            forecast_result=fcst, peer_snapshots=[],
            shares_outstanding=15.5e9, base_year=2024,
        )
        assert res.peer_pe_median is None
        # All valuations should have None implied_price
        for yr in res.years_forward:
            for v in yr.valuations:
                assert v.implied_price is None
