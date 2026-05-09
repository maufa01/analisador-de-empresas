"""
analysis/data_quality.py — completeness probes + healing tests.
"""
from __future__ import annotations
import pandas as pd

from analysis.data_quality import (
    assess_income_completeness,
    heal_income_statement,
    require_complete_income,
    CRITICAL_INCOME_FIELDS,
)


class TestCompleteness:

    def test_complete_income_passes(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "revenue":         [100, 110, 120],
            "operatingIncome": [25, 28, 31],
            "netIncome":       [18, 20, 22],
        }, index=idx)
        rep = assess_income_completeness(df)
        assert rep.is_complete
        assert rep.missing == []

    def test_missing_revenue_flagged(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "operatingIncome": [25, 28, 31],
            "netIncome":       [18, 20, 22],
        }, index=idx)
        rep = assess_income_completeness(df)
        assert not rep.is_complete
        assert "revenue" in rep.missing


class TestHealing:

    def test_heal_revenue_from_gross_plus_cost(self):
        """SEC EDGAR sometimes ships grossProfit + costOfRevenue but no
        explicit revenue column — heal reconstructs it."""
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "grossProfit":      [40, 44, 48],
            "costOfRevenue":    [60, 66, 72],
            "operatingIncome":  [25, 28, 31],
            "netIncome":        [18, 20, 22],
        }, index=idx)
        assert not assess_income_completeness(df).is_complete

        healed = heal_income_statement(df)
        assert assess_income_completeness(healed).is_complete
        assert healed["revenue"].iloc[0] == 100   # 40 + 60
        assert healed["revenue"].iloc[-1] == 120  # 48 + 72

    def test_heal_operating_income_from_gross_minus_opex(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "revenue":            [100, 110, 120],
            "grossProfit":        [40, 44, 48],
            "operatingExpenses":  [15, 16, 17],
            "netIncome":          [18, 20, 22],
        }, index=idx)
        healed = heal_income_statement(df)
        assert healed["operatingIncome"].iloc[0] == 25   # 40 − 15

    def test_heal_does_nothing_when_already_complete(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "revenue":         [100, 110, 120],
            "operatingIncome": [25, 28, 31],
            "netIncome":       [18, 20, 22],
        }, index=idx)
        healed = heal_income_statement(df)
        # Should be the same data
        assert healed["revenue"].equals(df["revenue"])

    def test_heal_empty_dataframe_safe(self):
        df = pd.DataFrame()
        healed = heal_income_statement(df)
        assert healed.empty


class TestRequireComplete:

    def test_returns_already_complete_unchanged(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "revenue":         [100, 110, 120],
            "operatingIncome": [25, 28, 31],
            "netIncome":       [18, 20, 22],
        }, index=idx)
        out, src = require_complete_income("AAPL", df, "sec_edgar")
        assert src == "sec_edgar"
        assert out["revenue"].iloc[0] == 100

    def test_heals_silently_when_possible(self):
        idx = pd.date_range("2020", periods=3, freq="YE")
        df = pd.DataFrame({
            "grossProfit":     [40, 44, 48],
            "costOfRevenue":   [60, 66, 72],
            "operatingIncome": [25, 28, 31],
            "netIncome":       [18, 20, 22],
        }, index=idx)
        out, src = require_complete_income("AAPL", df, "sec_edgar")
        assert "healed" in src
        assert out["revenue"].iloc[0] == 100
