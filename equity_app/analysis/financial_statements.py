"""
Standardised financial statements for the UI — built on top of
``data.edgar_provider.extract_financials``.

What this module owns:
    - Canonical line-item ordering + display labels per statement.
    - "Wide" view conversion (rows = line items, columns = period-ends,
      most-recent first) — easier to read and to chart.
    - Common-size analysis (income / balance as % of base line).
    - YoY % change matrix.

What it deliberately does NOT do:
    - Hit the network. ``extract_financials`` already caches at the
      provider layer.
    - Compute ratios. Those live in ``analysis.ratio_engine``.

Returned DataFrames use ``period_end`` Timestamps as columns and the
canonical snake_case line keys as the row index (e.g. "revenue",
"gross_profit", "total_assets"). The first column is the most recent
period.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# Canonical line items per statement
# (key, display_label, is_subtotal)
# ============================================================
INCOME_LINES: list[tuple[str, str, bool]] = [
    ("revenue",            "Revenue",                  True),
    ("cost_of_revenue",    "Cost of Revenue",          False),
    ("gross_profit",       "Gross Profit",             True),
    ("operating_income",   "Operating Income (EBIT)",  True),
    ("interest_expense",   "Interest Expense",         False),
    ("tax_expense",        "Tax Expense",              False),
    ("net_income",         "Net Income",               True),
    ("eps_basic",          "EPS Basic",                False),
    ("eps_diluted",        "EPS Diluted",              False),
    ("shares_diluted",     "Shares Diluted (avg)",     False),
    ("shares_outstanding", "Shares Outstanding",       False),
]

BALANCE_LINES: list[tuple[str, str, bool]] = [
    # Assets
    ("cash",                  "Cash & Equivalents",       False),
    ("short_term_investments", "Short-term Investments",  False),
    ("receivables",           "Accounts Receivable",      False),
    ("inventory",             "Inventory",                False),
    ("current_assets",        "Total Current Assets",     True),
    ("ppe_net",               "PP&E (Net)",               False),
    ("goodwill",              "Goodwill",                 False),
    ("intangibles",           "Intangibles",              False),
    ("total_assets",          "Total Assets",             True),
    # Liabilities
    ("accounts_payable",      "Accounts Payable",         False),
    ("current_liabilities",   "Total Current Liabilities", True),
    ("long_term_debt",        "Long-term Debt",           False),
    ("total_debt",            "Total Debt",               False),
    ("total_liabilities",     "Total Liabilities",        True),
    # Equity
    ("stockholders_equity",   "Stockholders Equity",      True),
]

CASHFLOW_LINES: list[tuple[str, str, bool]] = [
    ("operating_cash_flow",   "Operating Cash Flow",      True),
    ("capex",                 "Capital Expenditures",     False),
    ("free_cash_flow",        "Free Cash Flow (calc)",    True),
    ("investing_cash_flow",   "Investing Cash Flow",      True),
    ("dividends_paid",        "Dividends Paid",           False),
    ("stock_repurchased",     "Stock Buybacks",           False),
    ("stock_issued",          "Stock Issued",             False),
    ("financing_cash_flow",   "Financing Cash Flow",      True),
    ("depreciation",          "D&A",                      False),
]


@dataclass
class StandardisedStatements:
    income:               pd.DataFrame      # rows=line items, cols=periods (most-recent first)
    balance:              pd.DataFrame
    cashflow:             pd.DataFrame
    common_size_income:   pd.DataFrame      # % of revenue
    common_size_balance:  pd.DataFrame      # % of total assets
    yoy_income:           pd.DataFrame      # YoY % change for income items
    freq:                 str               # "annual" | "quarterly"
    note:                 str = ""


# ============================================================
# Internals
# ============================================================
def _to_wide(raw_df: pd.DataFrame, line_specs: list,
             *, freq: str) -> pd.DataFrame:
    """
    Convert the SEC long DataFrame (rows=dates, cols=metrics) to the
    UI's wide shape (rows=line items in canonical order, cols=dates
    descending).
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    # Sort dates descending so the first column is the most recent period
    df = raw_df.sort_index(ascending=False).copy()

    # Drop bookkeeping columns the SEC extractor adds for quarterly views
    for col in ("period", "form"):
        if col in df.columns:
            df = df.drop(columns=col)

    if df.empty:
        return pd.DataFrame()

    # Transpose: now rows=metrics, cols=dates (descending)
    wide = df.T

    # Filter + reorder rows to the canonical line-item list
    keys = [k for k, _, _ in line_specs]
    keep = [k for k in keys if k in wide.index]
    if not keep:
        return pd.DataFrame()
    wide = wide.loc[keep]

    # Coerce to float; non-numeric becomes NaN (defensive)
    wide = wide.apply(pd.to_numeric, errors="coerce")

    return wide


def _common_size(df: pd.DataFrame, base_line: str) -> pd.DataFrame:
    """Each line as % of ``base_line``. Returns empty DF if base is missing."""
    if df is None or df.empty or base_line not in df.index:
        return pd.DataFrame()
    base = df.loc[base_line]
    # Avoid divide-by-zero — np handles inf/nan
    out = (df.div(base.replace(0, pd.NA))) * 100.0
    return out


def _yoy(df: pd.DataFrame) -> pd.DataFrame:
    """YoY % change. Columns are dates DESCENDING, so YoY for col[i] is
    versus col[i+1] (the previous period)."""
    if df is None or df.empty or len(df.columns) < 2:
        return pd.DataFrame()
    # Reverse to ascending, pct_change along columns, reverse back
    asc = df.iloc[:, ::-1]
    pct = asc.pct_change(axis=1) * 100.0
    return pct.iloc[:, ::-1]


def _ensure_fcf(cashflow_wide: pd.DataFrame) -> pd.DataFrame:
    """Synthesize free_cash_flow row when only OCF + capex are reported."""
    if cashflow_wide.empty:
        return cashflow_wide
    if "free_cash_flow" in cashflow_wide.index:
        return cashflow_wide
    if "operating_cash_flow" not in cashflow_wide.index:
        return cashflow_wide
    ocf = cashflow_wide.loc["operating_cash_flow"]
    if "capex" in cashflow_wide.index:
        # Sign convention is provider-dependent: FMP reports capex as a
        # negative number (outflow), but SEC EDGAR's
        # PaymentsToAcquirePropertyPlantAndEquipment is positive (gross
        # payment). Using OCF − |capex| is correct under either convention
        # and matches free_cash_flow() in analysis/ratios.py.
        capex = cashflow_wide.loc["capex"]
        fcf = ocf - capex.abs()
    else:
        fcf = ocf
    out = cashflow_wide.copy()
    out.loc["free_cash_flow"] = fcf
    # Ensure free_cash_flow lands in the canonical position by reindexing
    keys_in_order = [k for k, _, _ in CASHFLOW_LINES if k in out.index]
    return out.loc[keys_in_order]


# ============================================================
# Public API
# ============================================================
def get_standardised_statements(
    ticker: str, *, freq: str = "annual",
) -> StandardisedStatements:
    """Pull SEC EDGAR financials and return them in the wide UI shape."""
    try:
        from data.edgar_provider import extract_financials
    except Exception as e:
        logger.warning(f"edgar_provider unavailable: {e}")
        empty = pd.DataFrame()
        return StandardisedStatements(
            income=empty, balance=empty, cashflow=empty,
            common_size_income=empty, common_size_balance=empty, yoy_income=empty,
            freq=freq, note="SEC EDGAR provider not available.",
        )

    raw = extract_financials(ticker, freq=freq) or {}
    income_w = _to_wide(raw.get("income", pd.DataFrame()), INCOME_LINES, freq=freq)
    balance_w = _to_wide(raw.get("balance", pd.DataFrame()), BALANCE_LINES, freq=freq)
    cash_w = _to_wide(raw.get("cashflow", pd.DataFrame()), CASHFLOW_LINES, freq=freq)
    cash_w = _ensure_fcf(cash_w)

    cs_income = _common_size(income_w, "revenue")
    cs_balance = _common_size(balance_w, "total_assets")
    yoy_income = _yoy(income_w)

    note = ""
    if income_w.empty and balance_w.empty and cash_w.empty:
        note = ("SEC EDGAR returned no statements for this ticker. "
                "Non-US issuers and recent IPOs are common reasons.")

    return StandardisedStatements(
        income=income_w,
        balance=balance_w,
        cashflow=cash_w,
        common_size_income=cs_income,
        common_size_balance=cs_balance,
        yoy_income=yoy_income,
        freq=freq,
        note=note,
    )


def display_label(line_key: str, statement: str = "income") -> str:
    """Look up the user-facing label for a canonical line key."""
    table: list[tuple[str, str, bool]] = {
        "income":   INCOME_LINES,
        "balance":  BALANCE_LINES,
        "cashflow": CASHFLOW_LINES,
    }.get(statement, [])
    for k, label, _ in table:
        if k == line_key:
            return label
    return line_key.replace("_", " ").title()
