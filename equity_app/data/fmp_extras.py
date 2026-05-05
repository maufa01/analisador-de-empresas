"""
FMP v3+v4 endpoints not covered by the core ``FMPProvider`` class —
insider trading, segment / geography revenue, extended earnings
calendar, ETF holders, institutional holders.

Same conservative posture as the rest of the data layer: every public
function returns an empty DataFrame (or empty dict) when the API key
isn't set, when the plan doesn't expose the endpoint (HTTP 403), or
when the request times out / 429s. Callers never see exceptions.

Why this lives in a separate module: ``fmp_provider.py`` is already a
production-grade ``DataProvider`` subclass. These are simpler, sparser
endpoints used only by the new Phase-5 analyses — colocating them
would crowd the core provider without benefit.
"""
from __future__ import annotations
from typing import Any, Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


_FMP_BASE = "https://financialmodelingprep.com/api"


# ============================================================
# Bottom-level HTTP — single helper used by every call below
# ============================================================
def _api_key() -> str:
    try:
        from core.config import settings
        return settings.fmp_api_key or ""
    except Exception:
        import os
        return os.environ.get("FMP_API_KEY", "") or ""


def _get(endpoint: str, params: Optional[dict] = None,
         version: str = "v3") -> Any:
    """Returns raw JSON or {} on any failure. NEVER raises."""
    key = _api_key()
    if not key:
        return {}

    try:
        import requests  # type: ignore
    except ImportError:
        return {}

    url = f"{_FMP_BASE}/{version}/{endpoint}"
    full = dict(params or {})
    full["apikey"] = key
    try:
        r = requests.get(url, params=full, timeout=15)
    except Exception as e:
        logger.debug(f"FMP request failed for {endpoint}: {e}")
        return {}
    if r.status_code == 403:
        # Endpoint not in plan — silently downgrade to "no data"
        return {}
    if r.status_code == 429:
        logger.warning("FMP rate-limited — backing off this call")
        return {}
    if r.status_code >= 400:
        return {}
    try:
        return r.json()
    except Exception:
        return {}


# ============================================================
# Insider transactions (v4)
# ============================================================
def fetch_insider_transactions(ticker: str, limit: int = 200) -> pd.DataFrame:
    """Form-4 transactions. Empty DataFrame on failure / no key / no plan."""
    data = _get("insider-trading", {"symbol": ticker, "limit": limit},
                version="v4")
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    # Normalise dates + value
    for col in ("transactionDate", "filingDate"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "securitiesTransacted" in df.columns and "price" in df.columns:
        df["transaction_value"] = (
            pd.to_numeric(df["securitiesTransacted"], errors="coerce").fillna(0)
            * pd.to_numeric(df["price"], errors="coerce").fillna(0)
        )
    return df.sort_values("transactionDate", ascending=False, na_position="last")


# ============================================================
# Revenue segmentation (v4)
# ============================================================
def _segmentation_to_dataframe(payload: Any) -> pd.DataFrame:
    """FMP returns [{date1: {seg1: v, seg2: v}}, …] — flatten to wide DF."""
    if not payload or not isinstance(payload, list):
        return pd.DataFrame()
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        for date_str, segments in item.items():
            if not isinstance(segments, dict):
                continue
            row = {"date": date_str}
            row.update({k: v for k, v in segments.items()
                        if isinstance(v, (int, float))})
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    return df


def fetch_revenue_by_segment(ticker: str) -> pd.DataFrame:
    payload = _get("revenue-product-segmentation",
                   {"symbol": ticker, "structure": "flat"},
                   version="v4")
    return _segmentation_to_dataframe(payload)


def fetch_revenue_by_geography(ticker: str) -> pd.DataFrame:
    payload = _get("revenue-geographic-segmentation",
                   {"symbol": ticker, "structure": "flat"},
                   version="v4")
    return _segmentation_to_dataframe(payload)


# ============================================================
# Earnings calendar (extended)
# ============================================================
def fetch_earnings_history(ticker: str, limit: int = 20) -> pd.DataFrame:
    """16+ quarters of EPS + revenue actual vs estimate."""
    data = _get(f"historical/earning_calendar/{ticker}", {"limit": limit})
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Compute surprises if estimates are present
    if "epsActual" in df.columns and "epsEstimated" in df.columns:
        ea = pd.to_numeric(df["epsActual"], errors="coerce")
        ee = pd.to_numeric(df["epsEstimated"], errors="coerce")
        df["eps_surprise"] = ea - ee
        df["eps_surprise_pct"] = (df["eps_surprise"] / ee.abs()) * 100
        df["beat_eps"] = ea > ee
    if "revenueActual" in df.columns and "revenueEstimated" in df.columns:
        ra = pd.to_numeric(df["revenueActual"], errors="coerce")
        re_ = pd.to_numeric(df["revenueEstimated"], errors="coerce")
        df["revenue_surprise"] = ra - re_
        df["revenue_surprise_pct"] = (df["revenue_surprise"] / re_.abs()) * 100
        df["beat_revenue"] = ra > re_
    return df.sort_values("date", ascending=False, na_position="last")


def fetch_analyst_estimates(ticker: str, period: str = "quarter") -> pd.DataFrame:
    data = _get(f"analyst-estimates/{ticker}", {"period": period})
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.sort_values("date", ascending=False, na_position="last")


# ============================================================
# ETF holders
# ============================================================
def fetch_etf_holders(ticker: str) -> pd.DataFrame:
    """Which ETFs hold this ticker, with weight + share counts."""
    data = _get(f"etf-holder/{ticker}")
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    for col in ("weightPercentage", "sharesNumber", "marketValue"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("weightPercentage", ascending=False, na_position="last")


# ============================================================
# Institutional holders + 13F changes
# ============================================================
def fetch_institutional_holders(ticker: str) -> pd.DataFrame:
    data = _get(f"institutional-holder/{ticker}")
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    for col in ("shares", "sharesNumber", "valueOfShares", "change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_institutional_ownership_changes(ticker: str) -> pd.DataFrame:
    """Quarter-over-quarter institutional ownership snapshots."""
    data = _get("institutional-ownership/symbol-ownership",
                {"symbol": ticker, "includeCurrentQuarter": True},
                version="v4")
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date", ascending=False)
    return df


def is_available() -> bool:
    """Cheap predicate the UI uses to decide between live data and the
    'configure FMP_API_KEY' empty state."""
    return bool(_api_key())
