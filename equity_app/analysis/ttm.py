"""
Trailing Twelve Months (TTM) computation.

For income statement and cash flow, TTM = sum of the last 4 quarters
(flow items). For balance sheet, TTM = most recent quarter (stock items
are point-in-time, not periodic accumulations).

Per-share metrics (EPS, weighted-avg shares) are STOCK in this module —
TTM EPS reported by FMP is the last quarter's diluted EPS, not a
running total. If the caller wants TTM EPS as net income / shares, they
should compute it from the returned series.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd


# Items that ACCUMULATE over the year (sum for TTM)
FLOW_ITEMS_INCOME: set[str] = {
    "revenue", "totalRevenue", "costOfRevenue", "grossProfit",
    "researchAndDevelopmentExpenses",
    "sellingGeneralAndAdministrativeExpenses",
    "operatingExpenses", "operatingIncome", "ebit", "ebitda",
    "interestIncome", "interestExpense", "incomeBeforeTax",
    "incomeTaxExpense", "netIncome", "depreciationAndAmortization",
}

FLOW_ITEMS_CASH: set[str] = {
    "operatingCashFlow", "netCashProvidedByOperatingActivities",
    "capitalExpenditure", "freeCashFlow",
    "stockBasedCompensation", "dividendsPaid",
    "commonStockRepurchased", "stockRepurchase",
    "acquisitionsNet", "depreciationAndAmortization",
    "changeInWorkingCapital", "debtRepayment",
    "netCashUsedForInvestingActivites",
    "netCashUsedProvidedByFinancingActivities",
    "commonStockIssued", "netIncome",
}

# Per-share metrics — return the most recent value, not summed
STOCK_ITEMS_INCOME: set[str] = {
    "weightedAverageShsOut", "weightedAverageShsOutDil",
    "eps", "epsdiluted",
}


def _last_n(quarterly: Optional[pd.DataFrame], n: int = 4) -> Optional[pd.DataFrame]:
    if quarterly is None or quarterly.empty:
        return None
    if len(quarterly) < n:
        return None
    return quarterly.sort_index().tail(n)


def compute_ttm_income(quarterly: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """Sum of last 4 quarters for flow items, last value for stock items.

    Unrecognised columns default to FLOW (sum) — most income-statement
    columns are flows. Identifier metadata columns (symbol, cik,
    filingDate, period, …) are non-numeric and excluded up-front.
    """
    last4 = _last_n(quarterly, 4)
    if last4 is None:
        return None
    last4_num = last4.select_dtypes(include="number")
    out = pd.Series(dtype=float)
    for col in last4_num.columns:
        if col in STOCK_ITEMS_INCOME:
            out[col] = float(last4_num[col].dropna().iloc[-1]) if last4_num[col].notna().any() else float("nan")
        else:
            out[col] = float(last4_num[col].sum(skipna=True))
    out.name = "TTM"
    return out


def compute_ttm_cash(quarterly: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """Sum last 4 quarters — every cash-flow item is a flow. Identifier
    metadata columns are non-numeric and excluded up-front."""
    last4 = _last_n(quarterly, 4)
    if last4 is None:
        return None
    last4_num = last4.select_dtypes(include="number")
    out = pd.Series(dtype=float)
    for col in last4_num.columns:
        out[col] = float(last4_num[col].sum(skipna=True))
    out.name = "TTM"
    return out


def compute_ttm_balance(quarterly: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """Balance-sheet items are stocks — return most recent quarter."""
    if quarterly is None or quarterly.empty:
        return None
    out = quarterly.sort_index().iloc[-1].copy()
    out.name = "TTM"
    return out
