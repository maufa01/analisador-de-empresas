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
import re
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
    """Every provider in the chain failed. Carries both the human-readable
    list of ``providers_tried`` (e.g. ``"fmp:missing_key (12ms)"``) AND
    the structured ``attempts`` list of :class:`ProviderResult` so the UI
    can render a per-provider table with status + latency + suggestion."""
    def __init__(
        self,
        message: str,
        providers_tried: list[str],
        attempts: Optional[list] = None,
    ):
        super().__init__(message)
        self.message = message
        self.providers_tried = list(providers_tried)
        self.attempts = list(attempts) if attempts is not None else []


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
        income  = prov.fetch_income_statement(ticker, years=5)
        balance = prov.fetch_balance_sheet(ticker, years=5)
        cash    = prov.fetch_cash_flow(ticker, years=5)
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
            # Heal the income statement post-fetch (P10.2 — fixes Revenue
            # NaN when EDGAR shipped XBRL aliases instead of FMP camelCase,
            # and EBITDA truncated to 2023+ for FMP-sourced data).
            try:
                from analysis.data_quality import heal_income_statement
                healed = heal_income_statement(bundle.income)
                if healed is not None:
                    bundle.income = healed
            except Exception:
                pass
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


import time
from functools import wraps as _wraps

from core.provider_status import ProviderResult, ProviderStatus


def _timed(fn):
    """Wrap a ProviderResult-returning func with latency measurement."""
    @_wraps(fn)
    def _inner(*args, **kwargs):
        t0 = time.time()
        result = fn(*args, **kwargs)
        if isinstance(result, ProviderResult):
            result.latency_ms = (time.time() - t0) * 1000.0
        return result
    return _inner


# ============================================================
# FMP — price + info (FIRST in both chains, single paid provider)
# ============================================================
@_timed
def _price_from_fmp(ticker: str) -> ProviderResult:
    try:
        from data.fmp_provider import FMPProvider
        from core.exceptions import (
            MissingAPIKeyError, RateLimitError, TickerNotFoundError,
        )
    except ImportError as e:
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=f"import: {e}")

    try:
        prov = FMPProvider()
    except MissingAPIKeyError:
        return ProviderResult(
            "fmp", ProviderStatus.MISSING_KEY,
            message="FMP_API_KEY not configured",
        )
    except Exception as e:
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=str(e))

    try:
        raw = prov._get(f"quote/{ticker.upper().strip()}")
    except RateLimitError as e:
        return ProviderResult("fmp", ProviderStatus.RATE_LIMITED, message=str(e))
    except MissingAPIKeyError as e:
        return ProviderResult("fmp", ProviderStatus.MISSING_KEY, message=str(e))
    except TickerNotFoundError:
        return ProviderResult(
            "fmp", ProviderStatus.TICKER_NOT_FOUND,
            message=f"FMP does not recognise {ticker}",
        )
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "connection" in msg:
            return ProviderResult("fmp", ProviderStatus.NETWORK_ERROR, message=str(e))
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=str(e))

    if not raw or not isinstance(raw, list) or not raw[0]:
        return ProviderResult(
            "fmp", ProviderStatus.NO_MATCH,
            message="quote endpoint returned empty",
        )

    q = raw[0]
    price = q.get("price")
    if price is None:
        return ProviderResult(
            "fmp", ProviderStatus.NO_MATCH,
            message="quote returned no price field",
        )

    try:
        cur = float(price)
    except (TypeError, ValueError):
        return ProviderResult(
            "fmp", ProviderStatus.NO_MATCH,
            message=f"unparseable price field: {price!r}",
        )
    pc = q.get("previousClose")
    try:
        prev = float(pc) if pc is not None else cur
    except (TypeError, ValueError):
        prev = cur
    change = cur - prev
    data = {
        "price":           cur,
        "previous_close":  prev,
        "change":          change,
        "change_pct":      float((change / prev * 100.0) if prev else 0.0),
        "open_today":      float(q.get("open") or 0.0),
        "high_today":      float(q.get("dayHigh") or 0.0),
        "low_today":       float(q.get("dayLow") or 0.0),
        "source":          "fmp",
        "is_realtime":     False,           # FMP free tier is 15-min delayed
        "fetched_at":      datetime.now(timezone.utc),
    }
    return ProviderResult("fmp", ProviderStatus.OK, data=data)


@_timed
def _price_from_finnhub(ticker: str) -> ProviderResult:
    """Real-time quote via Finnhub. Free tier: 60 req/min."""
    try:
        from data.finnhub_provider import is_available, fetch_quote
    except Exception as e:
        return ProviderResult("finnhub", ProviderStatus.UNKNOWN, message=str(e))
    if not is_available():
        return ProviderResult(
            "finnhub", ProviderStatus.MISSING_KEY,
            message="FINNHUB_API_KEY not configured",
        )
    try:
        q = fetch_quote(ticker)
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg:
            return ProviderResult("finnhub", ProviderStatus.RATE_LIMITED, message=str(e))
        if "401" in msg or "403" in msg:
            return ProviderResult("finnhub", ProviderStatus.MISSING_KEY, message=str(e))
        if "timeout" in msg or "connection" in msg:
            return ProviderResult("finnhub", ProviderStatus.NETWORK_ERROR, message=str(e))
        return ProviderResult("finnhub", ProviderStatus.UNKNOWN, message=str(e))
    if not isinstance(q, dict):
        return ProviderResult(
            "finnhub", ProviderStatus.NO_MATCH,
            message="fetch_quote returned non-dict",
        )
    cur = q.get("c")
    if not cur or not isinstance(cur, (int, float)) or cur <= 0:
        return ProviderResult(
            "finnhub", ProviderStatus.NO_MATCH,
            message=f"no valid price (c={cur!r})",
        )
    pc = q.get("pc") or 0.0
    data = {
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
    return ProviderResult("finnhub", ProviderStatus.OK, data=data)


@_timed
def _price_from_yfinance(ticker: str) -> ProviderResult:
    try:
        import yfinance as yf
    except ImportError:
        return ProviderResult("yfinance", ProviderStatus.UNKNOWN, message="not installed")
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
            prev = (full.get("regularMarketPreviousClose")
                    or full.get("previousClose") or cur)
            cur = float(cur) if cur else None
            prev = float(prev) if prev else cur
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg:
            return ProviderResult("yfinance", ProviderStatus.RATE_LIMITED, message=str(e))
        return ProviderResult("yfinance", ProviderStatus.UNKNOWN, message=str(e))
    if not cur or cur <= 0:
        return ProviderResult(
            "yfinance", ProviderStatus.SCRAPE_BLOCKED,
            message=f"no last_price returned (cur={cur!r}) — likely Yahoo scrape-block",
        )
    change = cur - (prev or cur)
    data = {
        "price":           float(cur),
        "previous_close":  float(prev or cur),
        "change":          float(change),
        "change_pct":      float((change / prev * 100) if prev else 0.0),
        "open_today":      0.0,
        "high_today":      0.0,
        "low_today":       0.0,
        "source":          "yfinance",
        "is_realtime":     False,           # yfinance is 15-min delayed
        "fetched_at":      datetime.now(timezone.utc),
    }
    return ProviderResult("yfinance", ProviderStatus.OK, data=data)


# ============================================================
# get_current_price — chain: FMP → Finnhub → yfinance
# ============================================================
def _diagnose_failure(
    ticker: str,
    attempts: list,
    *,
    kind: str,
) -> str:
    """Build a human-readable error message from the failed attempts."""
    statuses = {a.status for a in attempts}
    lines = [f"Could not fetch {kind} for {ticker}."]

    only_missing = (statuses == {ProviderStatus.MISSING_KEY})
    if only_missing:
        lines.append(
            "All providers report MISSING_KEY — set FMP_API_KEY and/or "
            "FINNHUB_API_KEY env vars (or in .streamlit/secrets.toml)."
        )
    elif ProviderStatus.TICKER_NOT_FOUND in statuses:
        lines.append(f"Ticker {ticker} may be delisted or invalid.")
    elif ProviderStatus.RATE_LIMITED in statuses:
        lines.append(
            "Rate-limited on at least one provider. Wait ~60 seconds and retry."
        )
    elif any(a.status == ProviderStatus.SCRAPE_BLOCKED
             for a in attempts if a.provider == "yfinance"):
        lines.append(
            "yfinance is currently scrape-blocked by Yahoo. FMP should be "
            "primary — verify FMP_API_KEY is set and valid."
        )
    return " ".join(lines)


def get_current_price(ticker: str) -> dict:
    """Live price via cascading chain. Order: FMP → Finnhub → yfinance.

    Raises :class:`DataSourceError` (with the full ``attempts`` list) when
    every provider fails — UI uses the structured info to render a
    per-provider diagnostic table.
    """
    if not ticker:
        raise DataSourceError("Empty ticker", [])

    attempts: list[ProviderResult] = []
    for fn in (_price_from_fmp, _price_from_finnhub, _price_from_yfinance):
        result = fn(ticker)
        attempts.append(result)
        if result.is_ok:
            data = dict(result.data)
            data["providers_tried"] = [r.to_label() for r in attempts]
            return data

    raise DataSourceError(
        message=_diagnose_failure(ticker, attempts, kind="price"),
        providers_tried=[r.to_label() for r in attempts],
        attempts=attempts,
    )


@_timed
def _info_from_fmp(ticker: str) -> ProviderResult:
    """FMP /profile — primary info source. Most reliable when key is set."""
    try:
        from data.fmp_provider import FMPProvider
        from core.exceptions import (
            MissingAPIKeyError, RateLimitError, TickerNotFoundError,
        )
    except ImportError as e:
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=f"import: {e}")

    try:
        prov = FMPProvider()
    except MissingAPIKeyError:
        return ProviderResult(
            "fmp", ProviderStatus.MISSING_KEY,
            message="FMP_API_KEY not configured",
        )
    except Exception as e:
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=str(e))

    try:
        p = prov.fetch_profile(ticker)
    except TickerNotFoundError:
        return ProviderResult(
            "fmp", ProviderStatus.TICKER_NOT_FOUND,
            message=f"FMP does not recognise {ticker}",
        )
    except RateLimitError as e:
        return ProviderResult("fmp", ProviderStatus.RATE_LIMITED, message=str(e))
    except MissingAPIKeyError as e:
        return ProviderResult("fmp", ProviderStatus.MISSING_KEY, message=str(e))
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "connection" in msg:
            return ProviderResult("fmp", ProviderStatus.NETWORK_ERROR, message=str(e))
        return ProviderResult("fmp", ProviderStatus.UNKNOWN, message=str(e))

    if not p or not p.get("companyName"):
        return ProviderResult(
            "fmp", ProviderStatus.NO_MATCH,
            message="profile endpoint returned empty",
        )

    # FMP's /profile ships the 52-week range as a "low-high" string.
    # Format varies: "90.93-161.34" (no spaces), "$90.93 - $161.34"
    # (currency + spaces), "0.5234 - 1.45". Strip commas (thousands
    # separators) then extract POSITIVE numeric tokens — the "-" in
    # "90.93-161.34" is the separator, never a sign, so we don't allow
    # leading "-" in the pattern.
    range_str = (p.get("range") or "").replace(",", "")
    nums = re.findall(r"\d+\.?\d*", range_str)
    nums = [float(n) for n in nums if n]
    nums = [n for n in nums if n > 0]  # 52W bounds are always positive
    if len(nums) >= 2:
        w52_low = min(nums)
        w52_high = max(nums)
    elif len(nums) == 1:
        w52_low = w52_high = nums[0]
    else:
        w52_low = w52_high = None

    data = {
        "name":               p.get("companyName"),
        "sector":             p.get("sector"),
        "industry":           p.get("industry"),
        "country":            p.get("country"),
        "exchange":           p.get("exchangeShortName") or p.get("exchange"),
        "website":            p.get("website"),
        "description":        p.get("description"),
        "employees":          p.get("fullTimeEmployees"),
        "market_cap":         p.get("mktCap") or p.get("marketCap"),
        # /profile carries shares as a separate field on some plans;
        # downstream code can also fall back to key_metrics.
        "shares_outstanding": _safe_int(p.get("sharesOutstanding")),
        "fifty_two_week_high": w52_high,
        "fifty_two_week_low":  w52_low,
        "beta":               p.get("beta"),
        "currency":           p.get("currency", "USD"),
        "ceo":                p.get("ceo"),
        "ipo":                p.get("ipoDate"),
        "city":               p.get("city"),
        "state":              p.get("state"),
        "source":             "fmp",
    }
    return ProviderResult("fmp", ProviderStatus.OK, data=data)


def _safe_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@_timed
def _info_from_yfinance(ticker: str) -> ProviderResult:
    try:
        import yfinance as yf
    except ImportError:
        return ProviderResult("yfinance", ProviderStatus.UNKNOWN, message="not installed")
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg:
            return ProviderResult("yfinance", ProviderStatus.RATE_LIMITED, message=str(e))
        return ProviderResult("yfinance", ProviderStatus.UNKNOWN, message=str(e))

    # Heuristic: a healthy yfinance .info dict has ~80+ keys. When Yahoo
    # blocks the scrape it returns a near-empty stub like {"trailingPegRatio": None}.
    if len(info) < 10:
        return ProviderResult(
            "yfinance", ProviderStatus.SCRAPE_BLOCKED,
            message=(f"info dict has {len(info)} keys (expected 80+) "
                     "— likely Yahoo scrape-block"),
        )
    name = info.get("longName") or info.get("shortName")
    if not name:
        return ProviderResult(
            "yfinance", ProviderStatus.SCRAPE_BLOCKED,
            message="info has keys but no longName / shortName",
        )

    data = {
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
        # Preserve the raw yfinance camelCase fields company_profile.py uses
        "longName":           info.get("longName"),
        "shortName":          info.get("shortName"),
        "longBusinessSummary": info.get("longBusinessSummary"),
        "companyOfficers":    info.get("companyOfficers", []),
        "city":               info.get("city"),
        "state":              info.get("state"),
        "source":             "yfinance",
    }
    return ProviderResult("yfinance", ProviderStatus.OK, data=data)


@_timed
def _info_from_finnhub(ticker: str) -> ProviderResult:
    """Finnhub /stock/profile2 — light company profile fallback."""
    try:
        from data.finnhub_provider import is_available, _get
    except Exception as e:
        return ProviderResult("finnhub", ProviderStatus.UNKNOWN, message=str(e))
    if not is_available():
        return ProviderResult(
            "finnhub", ProviderStatus.MISSING_KEY,
            message="FINNHUB_API_KEY not configured",
        )
    try:
        profile = _get("stock/profile2", {"symbol": ticker})
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg:
            return ProviderResult("finnhub", ProviderStatus.RATE_LIMITED, message=str(e))
        if "401" in msg or "403" in msg:
            return ProviderResult("finnhub", ProviderStatus.MISSING_KEY, message=str(e))
        if "timeout" in msg or "connection" in msg:
            return ProviderResult("finnhub", ProviderStatus.NETWORK_ERROR, message=str(e))
        return ProviderResult("finnhub", ProviderStatus.UNKNOWN, message=str(e))
    if not isinstance(profile, dict) or not profile.get("name"):
        return ProviderResult(
            "finnhub", ProviderStatus.NO_MATCH,
            message="profile2 returned empty / no 'name' field",
        )
    mcap = profile.get("marketCapitalization")
    shares = profile.get("shareOutstanding")
    data = {
        "name":               profile.get("name"),
        "industry":           profile.get("finnhubIndustry"),
        "country":            profile.get("country"),
        "exchange":           profile.get("exchange"),
        "website":            profile.get("weburl"),
        "logo":               profile.get("logo"),
        "ipo":                profile.get("ipo"),
        "market_cap":         (float(mcap) * 1e6) if isinstance(mcap, (int, float)) else None,
        "shares_outstanding": (float(shares) * 1e6) if isinstance(shares, (int, float)) else None,
        "source":             "finnhub",
    }
    return ProviderResult("finnhub", ProviderStatus.OK, data=data)


# ============================================================
# get_company_info — chain: FMP → yfinance → Finnhub
# ============================================================
def get_company_info(ticker: str) -> dict:
    """Sector / industry / market cap / 52w / etc. from the live chain.

    Order: FMP → yfinance → Finnhub. FMP is primary because it is the
    only paid provider and the most reliable; yfinance has the richest
    fields when it's not scrape-blocked; Finnhub is the safety net.

    Raises :class:`DataSourceError` (with structured ``attempts``) on
    full failure so the UI can render a per-provider diagnostic table.
    """
    if not ticker:
        raise DataSourceError("Empty ticker", [])

    attempts: list[ProviderResult] = []
    for fn in (_info_from_fmp, _info_from_yfinance, _info_from_finnhub):
        result = fn(ticker)
        attempts.append(result)
        if result.is_ok:
            data = dict(result.data)
            data["providers_tried"] = [r.to_label() for r in attempts]
            return data

    raise DataSourceError(
        message=_diagnose_failure(ticker, attempts, kind="company info"),
        providers_tried=[r.to_label() for r in attempts],
        attempts=attempts,
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

    # Cheap path: walk the same chain but stop at the first OK provider.
    for fn in (_info_from_fmp, _info_from_finnhub, _info_from_yfinance):
        result = fn(t)
        if result.is_ok:
            return {
                "valid":    True,
                "ticker":   t,
                "name":     result.data.get("name"),
                "exchange": result.data.get("exchange"),
            }
    raise ValueError(f"Ticker {t} not found in any provider")


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
