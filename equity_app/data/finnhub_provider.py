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
    """Returns parsed JSON or {} on any failure."""
    key = _api_key()
    if not key:
        return {}
    try:
        import requests  # type: ignore
    except ImportError:
        return {}

    full = dict(params or {})
    full["token"] = key
    try:
        r = requests.get(f"{_BASE_URL}/{endpoint}", params=full, timeout=15)
    except Exception as e:
        logger.debug(f"Finnhub request failed for {endpoint}: {e}")
        return {}
    if r.status_code == 429:
        logger.warning("Finnhub rate-limited — backing off this call")
        return {}
    if r.status_code != 200:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


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


def is_available() -> bool:
    return bool(_api_key())
