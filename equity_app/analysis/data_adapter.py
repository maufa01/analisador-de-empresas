"""
Data-source abstraction layer — LIVE-ONLY.

There are NO fixtures shipped to the user. Every value the page renders
comes from a real provider. When all providers fail, the adapter raises
``DataSourceError`` (with the list of providers tried) instead of silently
returning hardcoded data.

Provider chains (first non-None wins):
    Financials      :  SEC EDGAR → yfinance → FMP
    Current price   :  Finnhub   → yfinance
    Company info    :  yfinance  → Finnhub
    Insider tx      :  FMP                   (None when no key)
    Segments        :  FMP                   (None when no key)
    Geography       :  FMP                   (None when no key)
    Analyst est.    :  FMP                   (None when no key)
    ETF holders     :  FMP                   (None when no key)

The ``EQUITY_APP_DATA_SOURCE`` env var biases the financials chain:
``sec`` (default) / ``fmp`` / ``yfinance``. Order changes; nothing is
silenced.
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
# Live-only providers — fixtures intentionally removed.
# (tests/fixtures/*.py still exists but is consumed only by pytest;
#  the page no longer reads from it.)
# ============================================================


class DataSourceError(Exception):
    """Every provider in the chain failed. Surfaces the list it tried."""
    def __init__(self, message: str, providers_tried: list[str]):
        super().__init__(message)
        self.message = message
        self.providers_tried = list(providers_tried)


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
    """Returns 'sec' (default) / 'yfinance' / 'fmp'. Bias for the
    financials chain. ``fixtures`` is no longer a valid value — kept as
    a no-op string for backwards-compat env files."""
    src = os.environ.get("EQUITY_APP_DATA_SOURCE", "sec").lower()
    if src in ("sec", "fmp", "yfinance"):
        return src
    return "sec"


def get_financials(ticker: str) -> Optional[FinancialsBundle]:
    """
    Resolve financials for ``ticker``. Tries the preferred source first
    (env-controlled), then falls through to the others.

    Returns None when every provider in the chain returned None. Callers
    that need a hard error (instead of an empty state) should use
    ``require_financials`` below.
    """
    if not ticker:
        return None

    source = _preferred_source()
    if source == "sec":
        chain = [_from_sec, _from_yfinance, _from_fmp]
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


# ============================================================
# Live price / company info — REPLACES the page's _DEMO_* dicts
# ============================================================
from datetime import datetime, timezone


def _price_from_finnhub(ticker: str) -> Optional[dict]:
    """Real-time quote via Finnhub. Free tier: 60 req/min."""
    try:
        from data.finnhub_provider import is_available, fetch_quote
    except Exception:
        return None
    if not is_available():
        return None
    try:
        q = fetch_quote(ticker)
    except Exception:
        return None
    if not isinstance(q, dict):
        return None
    cur = q.get("c")
    if not cur or not isinstance(cur, (int, float)) or cur <= 0:
        return None
    pc = q.get("pc") or 0.0
    return {
        "price":           float(cur),
        "previous_close":  float(pc),
        "change":          float(q.get("d") or 0.0),
        "change_pct":      float(q.get("dp") or 0.0),
        "open_today":      float(q.get("o") or 0.0),
        "high_today":      float(q.get("h") or 0.0),
        "low_today":       float(q.get("l") or 0.0),
        "source":          "finnhub",
        "is_realtime":     True,
        "fetched_at":      datetime.now(timezone.utc),
    }


def _price_from_yfinance(ticker: str) -> Optional[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(ticker).fast_info
        cur = None
        prev = None
        try:
            cur = float(info.get("last_price")) if info.get("last_price") else None
            prev = float(info.get("previous_close")) if info.get("previous_close") else None
        except Exception:
            cur, prev = None, None
        if not cur:
            full = yf.Ticker(ticker).info or {}
            cur = full.get("regularMarketPrice") or full.get("currentPrice")
            prev = full.get("regularMarketPreviousClose") or full.get("previousClose") or cur
            cur = float(cur) if cur else None
            prev = float(prev) if prev else cur
    except Exception:
        return None
    if not cur or cur <= 0:
        return None
    change = cur - (prev or cur)
    return {
        "price":           float(cur),
        "previous_close":  float(prev or cur),
        "change":          float(change),
        "change_pct":      float((change / prev * 100) if prev else 0.0),
        "open_today":      0.0,
        "high_today":      0.0,
        "low_today":       0.0,
        "source":          "yfinance",
        "is_realtime":     False,           # yfinance is 15min delayed
        "fetched_at":      datetime.now(timezone.utc),
    }


def get_current_price(ticker: str) -> dict:
    """
    Real-time price via the live chain.

    Order: Finnhub (real-time) → yfinance (15-min delayed).
    Raises ``DataSourceError`` when both fail.
    """
    if not ticker:
        raise DataSourceError("Empty ticker", [])
    tried: list[str] = []
    for fn, name in ((_price_from_finnhub, "finnhub"),
                     (_price_from_yfinance, "yfinance")):
        try:
            data = fn(ticker)
        except Exception as e:
            tried.append(f"{name}:failed:{type(e).__name__}")
            continue
        if data is not None:
            tried.append(name)
            data["providers_tried"] = tried
            return data
        tried.append(f"{name}:no-data")
    raise DataSourceError(
        f"Could not fetch current price for {ticker}", tried,
    )


def _info_from_yfinance(ticker: str) -> Optional[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return None
    name = info.get("longName") or info.get("shortName")
    if not name:
        return None
    return {
        "name":               name,
        "sector":             info.get("sector"),
        "industry":           info.get("industry"),
        "country":            info.get("country"),
        "exchange":           info.get("exchange"),
        "website":            info.get("website"),
        "description":        info.get("longBusinessSummary"),
        "employees":          info.get("fullTimeEmployees"),
        "market_cap":         info.get("marketCap"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low":  info.get("fiftyTwoWeekLow"),
        "beta":               info.get("beta"),
        "pe_ratio":           info.get("trailingPE"),
        "forward_pe":         info.get("forwardPE"),
        "dividend_yield":     info.get("dividendYield"),
        "source":             "yfinance",
    }


def _info_from_finnhub(ticker: str) -> Optional[dict]:
    """Finnhub /stock/profile2 — light company profile fallback."""
    try:
        from data.finnhub_provider import is_available, _get
    except Exception:
        return None
    if not is_available():
        return None
    try:
        profile = _get("stock/profile2", {"symbol": ticker})
    except Exception:
        return None
    if not isinstance(profile, dict) or not profile.get("name"):
        return None
    mcap = profile.get("marketCapitalization")
    shares = profile.get("shareOutstanding")
    return {
        "name":               profile.get("name"),
        "industry":           profile.get("finnhubIndustry"),
        "country":            profile.get("country"),
        "exchange":           profile.get("exchange"),
        "website":            profile.get("weburl"),
        "logo":               profile.get("logo"),
        "ipo":                profile.get("ipo"),
        # Finnhub returns market cap in MILLIONS — normalise to absolute USD.
        "market_cap":         (float(mcap) * 1e6) if isinstance(mcap, (int, float)) else None,
        "shares_outstanding": (float(shares) * 1e6) if isinstance(shares, (int, float)) else None,
        "source":             "finnhub",
    }


def get_company_info(ticker: str) -> dict:
    """
    Sector / industry / market cap / 52w / etc. from the live chain.

    Order: yfinance → Finnhub. Raises ``DataSourceError`` on full failure.
    """
    if not ticker:
        raise DataSourceError("Empty ticker", [])
    tried: list[str] = []
    for fn, name in ((_info_from_yfinance, "yfinance"),
                     (_info_from_finnhub, "finnhub")):
        try:
            data = fn(ticker)
        except Exception as e:
            tried.append(f"{name}:failed:{type(e).__name__}")
            continue
        if data is not None:
            tried.append(name)
            data["providers_tried"] = tried
            return data
        tried.append(f"{name}:no-data")
    raise DataSourceError(
        f"Could not fetch company info for {ticker}", tried,
    )


def validate_ticker(ticker: str) -> dict:
    """
    Pre-flight: confirm ``ticker`` exists in some live provider.
    Returns ``{"valid": True, "name": ..., "exchange": ...}`` on hit;
    raises ``ValueError`` on miss / malformed input.
    """
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Empty or invalid ticker")
    t = ticker.upper().strip()
    if not t or len(t) > 10:
        raise ValueError(f"Invalid ticker format: {ticker!r}")

    # Cheap path: Finnhub /stock/profile2
    info = _info_from_finnhub(t)
    if info is None:
        info = _info_from_yfinance(t)
    if info is None:
        raise ValueError(f"Ticker {t} not found in any provider")
    return {
        "valid":    True,
        "ticker":   t,
        "name":     info.get("name"),
        "exchange": info.get("exchange"),
    }


def require_financials(ticker: str) -> FinancialsBundle:
    """Same as ``get_financials`` but raises ``DataSourceError`` instead
    of returning None — for call sites that prefer hard fail."""
    bundle = get_financials(ticker)
    if bundle is None:
        raise DataSourceError(
            f"Financials unavailable for {ticker} from every provider.",
            ["sec", "yfinance", "fmp"],
        )
    return bundle
