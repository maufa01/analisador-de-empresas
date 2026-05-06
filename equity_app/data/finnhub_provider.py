"""
Finnhub provider — quotes / company news / insider transactions /
analyst recommendations.

Free tier: 60 req/min. Returns empty / None on missing key, 429,
non-200 — never raises. The functions here are pure HTTP wrappers;
call sites in the analysis layer apply the business logic.

Endpoints touched:
    /quote                        — real-time quote
    /stock/insider-transactions   — Form-4 alternative (US only)
    /company-news                 — date-filtered news headlines
    /stock/recommendation         — analyst rec trends (12m)
    /news-sentiment               — proprietary sentiment per ticker
"""
from __future__ import annotations
from typing import Any, Optional

import logging
import pandas as pd

from core.config import read_secret

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"


# ============================================================
# HTTP wrapper
# ============================================================
def _api_key() -> str:
    return read_secret("FINNHUB_API_KEY", "")


def _get(endpoint: str, params: Optional[dict] = None) -> Any:
    """Returns parsed JSON or {} on any failure. Logged via api_logger."""
    import time as _time
    try:
        from utils.api_logger import log_api_request as _log
    except Exception:
        def _log(**kw): return None  # type: ignore[no-redef]

    ticker_arg = (params or {}).get("symbol") or (params or {}).get("symbols")
    key = _api_key()
    if not key:
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, error="no_api_key")
        return {}
    try:
        import requests  # type: ignore
    except ImportError:
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, error="requests_not_installed")
        return {}

    full = dict(params or {})
    full["token"] = key
    t0 = _time.monotonic()
    try:
        r = requests.get(f"{_BASE_URL}/{endpoint}", params=full, timeout=15)
    except Exception as e:
        elapsed = int((_time.monotonic() - t0) * 1000)
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, response_time_ms=elapsed,
             error=f"{type(e).__name__}: {e}")
        logger.debug(f"Finnhub request failed for {endpoint}: {e}")
        return {}
    elapsed = int((_time.monotonic() - t0) * 1000)
    if r.status_code == 429:
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, response_time_ms=elapsed, error="429 rate-limit")
        logger.warning("Finnhub rate-limited — backing off this call")
        return {}
    if r.status_code != 200:
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, response_time_ms=elapsed,
             error=f"HTTP {r.status_code}")
        return {}
    try:
        out = r.json()
    except ValueError:
        _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
             success=False, response_time_ms=elapsed, error="invalid_json")
        return {}
    summary = (f"200 OK · {len(out)} keys" if isinstance(out, dict)
               else f"200 OK · {len(out) if hasattr(out, '__len__') else '?'} items")
    _log(provider="finnhub", endpoint=endpoint, ticker=ticker_arg,
         success=True, response_time_ms=elapsed, response_summary=summary)
    return out


# ============================================================
# Public endpoints
# ============================================================
def fetch_quote(ticker: str) -> dict:
    """Real-time quote: c=current, h=high, l=low, o=open, pc=prev close."""
    return _get("quote", {"symbol": ticker})


def fetch_insider_transactions(ticker: str) -> pd.DataFrame:
    """Insider transactions — alternative to FMP / SEC Form 4 raw parsing.
    Finnhub returns aggregated transactions with name/share/value already
    split out, much cheaper than parsing every Form 4 XML individually."""
    payload = _get("stock/insider-transactions", {"symbol": ticker})
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "transactionDate" in df.columns:
        df["transactionDate"] = pd.to_datetime(df["transactionDate"], errors="coerce")
    if "filingDate" in df.columns:
        df["filingDate"] = pd.to_datetime(df["filingDate"], errors="coerce")
    return df.sort_values("transactionDate", ascending=False, na_position="last")


def fetch_company_news(ticker: str, *, days_back: int = 30) -> pd.DataFrame:
    """Headlines for the last N days."""
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    start = today - timedelta(days=days_back)
    payload = _get("company-news", {
        "symbol": ticker,
        "from":   start.isoformat(),
        "to":     today.isoformat(),
    })
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()
    df = pd.DataFrame(payload)
    if "datetime" in df.columns:
        df["published"] = pd.to_datetime(df["datetime"], unit="s", utc=True, errors="coerce")
        df = df.sort_values("published", ascending=False)
    return df


def fetch_recommendation_trends(ticker: str) -> pd.DataFrame:
    """Last 12 months of analyst recommendations (buy / hold / sell counts)."""
    payload = _get("stock/recommendation", {"symbol": ticker})
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()
    df = pd.DataFrame(payload)
    if "period" in df.columns:
        df["period"] = pd.to_datetime(df["period"], errors="coerce")
    return df.sort_values("period", ascending=False, na_position="last")


def fetch_news_sentiment(ticker: str) -> dict:
    """Finnhub's proprietary sentiment — buzz + sentiment score per ticker."""
    return _get("news-sentiment", {"symbol": ticker})


def fetch_earnings_calendar(ticker: str, *,
                            from_date: Optional[str] = None,
                            to_date: Optional[str] = None) -> pd.DataFrame:
    """Upcoming earnings dates + EPS estimates."""
    from datetime import datetime, timedelta
    if from_date is None:
        from_date = datetime.utcnow().date().isoformat()
    if to_date is None:
        to_date = (datetime.utcnow().date() + timedelta(days=90)).isoformat()
    payload = _get("calendar/earnings", {
        "symbol": ticker, "from": from_date, "to": to_date,
    })
    rows = payload.get("earningsCalendar") if isinstance(payload, dict) else None
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date", ascending=True, na_position="last")
    return df.reset_index(drop=True)


def fetch_price_target(ticker: str) -> dict:
    """Wall Street consensus price target (mean / high / low / num analysts)."""
    return _get("stock/price-target", {"symbol": ticker})


def fetch_senate_trading(ticker: str) -> pd.DataFrame:
    """Congressional trading filings for the ticker (US politicians)."""
    payload = _get("stock/congressional-trading", {"symbol": ticker})
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ("transactionDate", "filingDate"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "transactionDate" in df.columns:
        df = df.sort_values("transactionDate", ascending=False, na_position="last")
    return df.reset_index(drop=True)


def fetch_esg_scores(ticker: str) -> dict:
    """ESG scores: total + environment + social + governance."""
    return _get("stock/esg", {"symbol": ticker})


def fetch_basic_financials(ticker: str) -> dict:
    """All metrics endpoint — returns {'metric': {...}} with TTM ratios.
    Useful as a fallback when yfinance is missing a specific metric."""
    return _get("stock/metric", {"symbol": ticker, "metric": "all"})


def is_available() -> bool:
    return bool(_api_key())
