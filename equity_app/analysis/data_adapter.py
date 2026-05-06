"""
Data-source abstraction layer.

The app currently reads financials from local fixtures (demo set) and
yfinance (live). When the FMP provider is wired in, callers won't have
to care which source served the data — they ask the adapter for what
they need and get back a uniform shape.

Today's behaviour:
- ``get_financials(ticker)`` → tries the local fixture set first
  (AAPL/MSFT/JPM), then yfinance, returning whichever has data.
- ``get_insider_transactions``, ``get_segments``, ``get_analyst_estimates``
  return ``None`` until FMP is online — callers should branch on
  ``None`` and render a "Coming soon" placeholder.

Switching the default source later is a one-liner — set the
``EQUITY_APP_DATA_SOURCE`` env var to ``"fmp"`` and fill in the
``_fmp_*`` adapters.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from data.market_data import _yfinance


SourceName = Literal["yfinance", "fmp", "fixtures"]


@dataclass
class FinancialsBundle:
    """The shape every caller agrees on: 3 DataFrames in FMP camelCase."""
    income:  pd.DataFrame
    balance: pd.DataFrame
    cash:    pd.DataFrame
    source:  SourceName
    note:    str = ""


# ============================================================
# Internals
# ============================================================
def _from_fixtures(ticker: str) -> Optional[FinancialsBundle]:
    """Return the bundle for AAPL/MSFT/JPM; None for anything else."""
    try:
        from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023
    except Exception:
        return None
    table = {
        "AAPL": aapl_fy2023, "MSFT": msft_fy2023, "JPM": jpm_fy2023,
    }
    mod = table.get(ticker.upper())
    if mod is None:
        return None
    return FinancialsBundle(
        income=mod.income(), balance=mod.balance(), cash=mod.cash_flow(),
        source="fixtures",
    )


def _yf_to_camelcase(yf_df: pd.DataFrame) -> pd.DataFrame:
    """
    yfinance ships financials with rows = line items, columns = period
    end dates. Transpose so each row is a period and each column a
    line item, then rename to FMP camelCase keys the rest of the app
    expects.
    """
    if yf_df is None or not isinstance(yf_df, pd.DataFrame) or yf_df.empty:
        return pd.DataFrame()
    df = yf_df.T.copy()                                    # rows = periods now
    rename = {
        # ---- Income ----
        "Total Revenue":                                  "revenue",
        "Cost Of Revenue":                                "costOfRevenue",
        "Gross Profit":                                   "grossProfit",
        "Operating Income":                               "operatingIncome",
        "EBIT":                                           "ebit",
        "EBITDA":                                         "ebitda",
        "Net Income":                                     "netIncome",
        "Net Income Common Stockholders":                 "netIncome",
        "Selling General And Administration":             "sellingGeneralAndAdministrativeExpenses",
        "Selling General And Administrative":             "sellingGeneralAndAdministrativeExpenses",
        "Interest Expense":                               "interestExpense",
        "Tax Provision":                                  "incomeTaxExpense",
        "Diluted Average Shares":                         "weightedAverageShsOut",
        "Basic EPS":                                      "eps",
        "Diluted EPS":                                    "epsdiluted",
        # ---- Balance ----
        "Total Assets":                                   "totalAssets",
        "Current Assets":                                 "totalCurrentAssets",
        "Current Liabilities":                            "totalCurrentLiabilities",
        "Cash And Cash Equivalents":                      "cashAndCashEquivalents",
        "Cash Cash Equivalents And Short Term Investments": "cashAndShortTermInvestments",
        "Stockholders Equity":                            "totalStockholdersEquity",
        "Total Stockholder Equity":                       "totalStockholdersEquity",
        "Total Debt":                                     "totalDebt",
        "Long Term Debt":                                 "longTermDebt",
        "Net Receivables":                                "netReceivables",
        "Inventory":                                      "inventory",
        "Net PPE":                                        "propertyPlantEquipmentNet",
        "Goodwill":                                       "goodwill",
        "Intangible Assets":                              "intangibleAssets",
        "Total Liabilities Net Minority Interest":        "totalLiabilities",
        # ---- Cash flow ----
        "Operating Cash Flow":                            "operatingCashFlow",
        "Capital Expenditure":                            "capitalExpenditure",
        "Free Cash Flow":                                 "freeCashFlow",
        "Stock Based Compensation":                       "stockBasedCompensation",
        "Common Stock Dividend Paid":                     "dividendsPaid",
        "Repurchase Of Capital Stock":                    "commonStockRepurchased",
        "Reconciled Depreciation":                        "depreciationAndAmortization",
        "Depreciation And Amortization":                  "depreciationAndAmortization",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df.sort_index()


def _from_yfinance(ticker: str) -> Optional[FinancialsBundle]:
    yf = _yfinance()
    if yf is None or not ticker:
        return None
    try:
        t = yf.Ticker(ticker)
        income  = _yf_to_camelcase(getattr(t, "financials", None))
        balance = _yf_to_camelcase(getattr(t, "balance_sheet", None))
        cash    = _yf_to_camelcase(getattr(t, "cashflow", None))
    except Exception:
        return None
    if income.empty and balance.empty and cash.empty:
        return None
    return FinancialsBundle(
        income=income, balance=balance, cash=cash, source="yfinance",
    )


_SEC_TO_CAMEL = {
    # Income
    "revenue":              "revenue",
    "cost_of_revenue":      "costOfRevenue",
    "gross_profit":         "grossProfit",
    "operating_income":     "operatingIncome",
    "net_income":           "netIncome",
    "eps_basic":            "eps",
    "eps_diluted":          "epsdiluted",
    "shares_diluted":       "weightedAverageShsOut",
    "shares_basic":         "weightedAverageShsOutBasic",
    "tax_expense":          "incomeTaxExpense",
    "interest_expense":     "interestExpense",
    # Balance
    "total_assets":         "totalAssets",
    "current_assets":       "totalCurrentAssets",
    "cash":                 "cashAndCashEquivalents",
    "short_term_investments": "shortTermInvestments",
    "receivables":          "netReceivables",
    "inventory":            "inventory",
    "ppe_net":              "propertyPlantEquipmentNet",
    "goodwill":             "goodwill",
    "intangibles":          "intangibleAssets",
    "total_liabilities":    "totalLiabilities",
    "current_liabilities":  "totalCurrentLiabilities",
    "accounts_payable":     "accountsPayable",
    "long_term_debt":       "longTermDebt",
    "total_debt":           "totalDebt",
    "stockholders_equity":  "totalStockholdersEquity",
    "shares_outstanding":   "commonStockSharesOutstanding",
    # Cash flow
    "operating_cash_flow":  "operatingCashFlow",
    "investing_cash_flow":  "investingCashFlow",
    "financing_cash_flow":  "financingCashFlow",
    "capex":                "capitalExpenditure",
    "depreciation":         "depreciationAndAmortization",
    "dividends_paid":       "dividendsPaid",
    "stock_repurchased":    "commonStockRepurchased",
    "stock_issued":         "commonStockIssued",
}


def _sec_df_to_camelcase(df: pd.DataFrame) -> pd.DataFrame:
    """Rename SEC EDGAR snake_case cols to FMP camelCase + drop bookkeeping."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.drop(columns=["period", "form"], errors="ignore")
    return df.rename(columns={k: v for k, v in _SEC_TO_CAMEL.items()
                              if k in df.columns})


def _from_sec(ticker: str) -> Optional[FinancialsBundle]:
    """SEC EDGAR — official US-listed financials, no key needed."""
    try:
        from data.edgar_provider import extract_financials
    except Exception:
        return None
    try:
        bundle = extract_financials(ticker, freq="annual")
    except Exception:
        return None
    income  = _sec_df_to_camelcase(bundle.get("income", pd.DataFrame()))
    balance = _sec_df_to_camelcase(bundle.get("balance", pd.DataFrame()))
    cash    = _sec_df_to_camelcase(bundle.get("cashflow", pd.DataFrame()))
    if income.empty and balance.empty and cash.empty:
        return None
    return FinancialsBundle(
        income=income, balance=balance, cash=cash, source="fmp",
        # We label the source 'fmp' so downstream FMP-shape readers don't
        # have to special-case 'sec'. The actual provenance is exposed in
        # the bundle's note field.
        note=("Source: SEC EDGAR XBRL (Company Facts). "
              "Official annual filings — coverage from 1993+ for many filers."),
    )


def _from_fmp(ticker: str) -> Optional[FinancialsBundle]:
    """Use the existing FMPProvider class. Returns None when the key
    isn't set or the request fails — the caller will fall through to
    yfinance via the chain in ``get_financials``."""
    try:
        from data.fmp_provider import FMPProvider
        from core.exceptions import MissingAPIKeyError, TickerNotFoundError, ProviderError
    except Exception:
        return None
    try:
        prov = FMPProvider()
        income  = prov.fetch_income_statement(ticker, years=10)
        balance = prov.fetch_balance_sheet(ticker, years=10)
        cash    = prov.fetch_cash_flow(ticker, years=10)
    except (MissingAPIKeyError, TickerNotFoundError, ProviderError):
        return None
    except Exception:
        return None
    if income.empty and balance.empty and cash.empty:
        return None
    return FinancialsBundle(
        income=income, balance=balance, cash=cash, source="fmp",
    )


# ============================================================
# Public API
# ============================================================
def _preferred_source() -> str:
    """`'sec'` is preferred when the env hints at it. Returns one of
    'fixtures' / 'yfinance' / 'fmp' / 'sec'. Resolution chain in
    ``get_financials`` uses this only as a hint about ordering."""
    src = os.environ.get("EQUITY_APP_DATA_SOURCE", "fixtures").lower()
    if src in ("sec", "fmp", "yfinance", "fixtures"):
        return src
    return "fixtures"


def get_financials(ticker: str) -> Optional[FinancialsBundle]:
    """
    Resolve financials for ``ticker``. Tries the preferred source first
    (env-controlled), then falls through to the others.

    Returns None when nothing has data — callers should render an
    empty-state. Demo fixtures (AAPL/MSFT/JPM) always win when present
    so the app behaves deterministically without hitting the network.
    """
    if not ticker:
        return None

    fixture = _from_fixtures(ticker)
    if fixture is not None:
        return fixture

    source = _preferred_source()
    if source == "sec":
        chain = [_from_sec, _from_fmp, _from_yfinance]
    elif source == "fmp":
        chain = [_from_fmp, _from_sec, _from_yfinance]
    else:
        chain = [_from_yfinance, _from_sec, _from_fmp]
    for fn in chain:
        bundle = fn(ticker)
        if bundle is not None:
            return bundle
    return None


# ---- FMP-only endpoints ----
# All four return None when FMP_API_KEY is not configured (graceful no-op).
# Callers branch on None and render an empty state.
def get_insider_transactions(ticker: str) -> Optional[pd.DataFrame]:
    """Form 4 transactions from FMP v4 — empty DataFrame is also returned
    as None so callers have a single sentinel to check."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_insider_transactions(ticker, limit=200)
    return df if not df.empty else None


def get_segments(ticker: str) -> Optional[pd.DataFrame]:
    """Revenue by product segment from FMP v4."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_revenue_by_segment(ticker)
    return df if not df.empty else None


def get_geography(ticker: str) -> Optional[pd.DataFrame]:
    """Revenue by region from FMP v4."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_revenue_by_geography(ticker)
    return df if not df.empty else None


def get_analyst_estimates(ticker: str, period: str = "quarter") -> Optional[pd.DataFrame]:
    """Forward consensus EPS / revenue from FMP."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_analyst_estimates(ticker, period=period)
    return df if not df.empty else None


def get_etf_holders(ticker: str) -> Optional[pd.DataFrame]:
    """Which ETFs hold this ticker — FMP only."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_etf_holders(ticker)
    return df if not df.empty else None


def get_extended_earnings_history(ticker: str, limit: int = 20) -> Optional[pd.DataFrame]:
    """16+ quarters of EPS + revenue actuals/estimates — FMP only."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    df = fmp_extras.fetch_earnings_history(ticker, limit=limit)
    return df if not df.empty else None


def fmp_available() -> bool:
    """True iff FMP_API_KEY is set — UI uses this to decide between live
    data and the 'configure FMP' empty state."""
    try:
        from data import fmp_extras
        return fmp_extras.is_available()
    except Exception:
        return False
