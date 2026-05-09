"""
Pytest fixtures shared across the test suite.

Adds the project root to sys.path so ``from core.config import settings``
works without installing the package. Fixtures here are dependency-light
to keep CI fast — heavier integration fixtures live in tests/fixtures/.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


# ============================================================
# Sample financials — minimal AAPL FY2023 shape
# Used by analysis/valuation tests in later sessions.
# ============================================================
@pytest.fixture
def sample_income_aapl_2023():
    import pandas as pd
    rows = [
        {"date": "2023-09-30", "revenue": 383285_000_000, "grossProfit": 169148_000_000,
         "operatingIncome": 114301_000_000, "netIncome": 96995_000_000,
         "ebitda": 129564_000_000, "eps": 6.16},
        {"date": "2022-09-30", "revenue": 394328_000_000, "grossProfit": 170782_000_000,
         "operatingIncome": 119437_000_000, "netIncome": 99803_000_000,
         "ebitda": 133138_000_000, "eps": 6.15},
        {"date": "2021-09-30", "revenue": 365817_000_000, "grossProfit": 152836_000_000,
         "operatingIncome": 108949_000_000, "netIncome": 94680_000_000,
         "ebitda": 123136_000_000, "eps": 5.67},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


@pytest.fixture
def sample_balance_aapl_2023():
    import pandas as pd
    rows = [
        {"date": "2023-09-30", "totalAssets": 352755_000_000,
         "totalLiabilities": 290437_000_000, "totalEquity": 62146_000_000,
         "totalDebt": 111088_000_000,
         "cashAndCashEquivalents": 29965_000_000,
         "totalCurrentAssets": 143566_000_000,
         "totalCurrentLiabilities": 145308_000_000},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


@pytest.fixture
def sample_cashflow_aapl_2023():
    import pandas as pd
    rows = [
        {"date": "2023-09-30", "operatingCashFlow": 110543_000_000,
         "capitalExpenditure": -10959_000_000,
         "stockBasedCompensation": 10833_000_000,
         "freeCashFlow": 99584_000_000},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


# ============================================================
# Stub provider helpers — used by test_finviz / test_fmp
# ============================================================
@pytest.fixture
def make_finviz_fundament():
    """Factory returning a Finviz-shaped fundamental dict."""
    def _make(**overrides):
        base = {
            "Company": "Apple Inc.",
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
            "Country": "USA",
            "Market Cap": "3.50T",
            "Price": "230.50",
            "Change": "1.25%",
            "Volume": "45,123,456",
            "P/E": "32.10",
            "Forward P/E": "29.40",
            "PEG": "2.10",
            "P/B": "55.20",
            "Beta": "1.20",
            "EPS (ttm)": "6.16",
            "Dividend %": "0.50%",
            "Range": "228.10 - 232.30",
            "52W Range": "164.00 - 240.00",
            "Short Float": "0.65%",
        }
        base.update(overrides)
        return base
    return _make


@pytest.fixture
def make_fmp_quote():
    """Factory returning an FMP-shaped quote payload (single-element list)."""
    def _make(**overrides):
        base = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "price": 230.50,
            "change": 2.85,
            "changePercentage": 1.25,
            "volume": 45_123_456,
            "marketCap": 3_500_000_000_000,
            "pe": 32.1,
            "dayHigh": 232.30,
            "dayLow": 228.10,
            "yearHigh": 240.0,
            "yearLow": 164.0,
        }
        base.update(overrides)
        return [base]
    return _make
