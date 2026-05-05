"""
analysis/fundamentals_check.py — coherence-check tests.

The check pipeline must be lenient (it's used pre-modeling, not at the
data boundary) but must catch real corruption: BS not balancing by more
than 1% of total assets, missing critical fields, non-monotonic indices.
"""
from __future__ import annotations
import pandas as pd
import pytest

from analysis.fundamentals_check import (
    Issue, CoherenceReport,
    coherence_report,
    check_balance_sheet_identity, check_critical_fields,
    check_index_integrity, check_sign_sanity,
)
from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023


# ============================================================
# Snapshot — clean fixtures must pass
# ============================================================
class TestSnapshotCleanFixtures:

    def test_aapl_passes(self):
        rep = coherence_report(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert rep.is_valid
        assert not rep.has_errors

    def test_msft_passes(self):
        rep = coherence_report(
            msft_fy2023.income(), msft_fy2023.balance(), msft_fy2023.cash_flow()
        )
        assert rep.is_valid

    def test_jpm_passes(self):
        # JPM balance is huge but balanced
        rep = coherence_report(
            jpm_fy2023.income(), jpm_fy2023.balance(), jpm_fy2023.cash_flow()
        )
        assert rep.is_valid


# ============================================================
# BS identity
# ============================================================
class TestBalanceSheetIdentity:

    def test_clean_bs_no_issue(self):
        idx = pd.to_datetime(["2023-12-31"])
        bal = pd.DataFrame({
            "totalAssets":             [1000.0],
            "totalLiabilities":         [600.0],
            "totalStockholdersEquity":  [400.0],
        }, index=idx)
        assert check_balance_sheet_identity(bal) is None

    def test_unbalanced_warning(self):
        idx = pd.to_datetime(["2023-12-31"])
        bal = pd.DataFrame({
            "totalAssets":             [1000.0],
            "totalLiabilities":         [500.0],
            "totalStockholdersEquity":  [400.0],   # off by 100 (10% of TA)
        }, index=idx)
        issue = check_balance_sheet_identity(bal)
        assert issue is not None
        assert issue.severity == "error"   # >5% drift => error

    def test_small_drift_warning_only(self):
        idx = pd.to_datetime(["2023-12-31"])
        bal = pd.DataFrame({
            "totalAssets":             [1000.0],
            "totalLiabilities":         [580.0],
            "totalStockholdersEquity":  [400.0],   # off by 20 (2%)
        }, index=idx)
        issue = check_balance_sheet_identity(bal)
        assert issue is not None
        assert issue.severity == "warning"

    def test_returns_none_when_total_liabilities_missing(self):
        idx = pd.to_datetime(["2023-12-31"])
        bal = pd.DataFrame({
            "totalAssets":             [1000.0],
            "totalStockholdersEquity":  [400.0],
        }, index=idx)
        assert check_balance_sheet_identity(bal) is None


# ============================================================
# Critical fields
# ============================================================
class TestCriticalFields:

    def test_all_present(self):
        issues = check_critical_fields(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert issues == []

    def test_missing_revenue(self):
        issues = check_critical_fields(
            pd.DataFrame(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        codes = [i.code for i in issues]
        assert "MISSING_REVENUE" in codes

    def test_missing_assets(self):
        issues = check_critical_fields(
            aapl_fy2023.income(), pd.DataFrame(), aapl_fy2023.cash_flow()
        )
        codes = [i.code for i in issues]
        assert "MISSING_TOTAL_ASSETS" in codes


# ============================================================
# Sign sanity
# ============================================================
class TestSignSanity:

    def test_positive_passes(self):
        assert check_sign_sanity(aapl_fy2023.income(), aapl_fy2023.balance()) == []

    def test_non_positive_revenue_flags(self):
        idx = pd.to_datetime(["2023-12-31"])
        inc = pd.DataFrame({"revenue": [-100.0]}, index=idx)
        bal = pd.DataFrame({"totalAssets": [1000.0]}, index=idx)
        issues = check_sign_sanity(inc, bal)
        codes = [i.code for i in issues]
        assert "REVENUE_NON_POSITIVE" in codes


# ============================================================
# Index integrity
# ============================================================
class TestIndexIntegrity:

    def test_monotonic_passes(self):
        idx = pd.to_datetime(["2021-12-31", "2022-12-31", "2023-12-31"])
        df = pd.DataFrame({"x": [1, 2, 3]}, index=idx)
        assert check_index_integrity(df, "income") is None

    def test_duplicate_flagged_error(self):
        idx = pd.to_datetime(["2022-12-31", "2022-12-31"])
        df = pd.DataFrame({"x": [1, 2]}, index=idx)
        issue = check_index_integrity(df, "income")
        assert issue is not None
        assert issue.severity == "error"
        assert issue.code == "INDEX_DUPLICATE"

    def test_unsorted_flagged_warning(self):
        idx = pd.to_datetime(["2023-12-31", "2022-12-31"])
        df = pd.DataFrame({"x": [1, 2]}, index=idx)
        issue = check_index_integrity(df, "income")
        assert issue is not None
        assert issue.severity == "warning"


# ============================================================
# Report aggregation
# ============================================================
class TestCoherenceReport:

    def test_valid_when_no_errors(self):
        rep = coherence_report(
            aapl_fy2023.income(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert rep.is_valid

    def test_invalid_when_critical_field_missing(self):
        rep = coherence_report(
            pd.DataFrame(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        assert not rep.is_valid
        assert rep.has_errors

    def test_by_severity_filtering(self):
        rep = coherence_report(
            pd.DataFrame(), aapl_fy2023.balance(), aapl_fy2023.cash_flow()
        )
        errors = rep.by_severity("error")
        assert len(errors) >= 1
        assert all(i.severity == "error" for i in errors)
