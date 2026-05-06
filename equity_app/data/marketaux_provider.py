"""
Marketaux provider — financial news with per-ticker sentiment.

Free tier: 100 requests/day. We treat that as scarce — call sites
should cache aggressively. Functions return empty / None on missing
key, 429, or non-200; never raise.

Endpoint: ``/news/all`` filtered by ``symbols``.

Sentiment: each article carries an `entities[].sentiment_score` in
[-1, +1] for the relevant ticker, plus a `sentiment_label` string.
"""
from __future__ import annotations
from typing import Any, Optional

import logging
import pandas as pd

from core.config import read_secret

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.marketaux.com/v1"


def _api_key() -> str:
    return read_secret("MARKETAUX_API_KEY", "")


def _get(endpoint: str, params: Optional[dict] = None) -> Any:
    key = _api_key()
    if not key:
        return {}
    try:
        import requests  # type: ignore
    except ImportError:
        return {}
    full = dict(params or {})
    full["api_token"] = key
    try:
        r = requests.get(f"{_BASE_URL}/{endpoint}", params=full, timeout=15)
    except Exception as e:
        logger.debug(f"Marketaux request failed for {endpoint}: {e}")
        return {}
    if r.status_code == 429:
        logger.warning("Marketaux daily quota hit — backing off this call")
        return {}
    if r.status_code != 200:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


def fetch_news(ticker: str, *, limit: int = 20,
               filter_us_only: bool = True) -> pd.DataFrame:
    """Per-ticker news with sentiment. ``limit`` capped at 100 per call."""
    params: dict = {
        "symbols":  ticker,
        "language": "en",
        "limit":    min(int(limit), 100),
    }
    if filter_us_only:
        params["countries"] = "us"

    payload = _get("news/all", params)
    articles = payload.get("data") if isinstance(payload, dict) else None
    if not articles:
        return pd.DataFrame()

    rows = []
    for art in articles:
        entities = art.get("entities") or []
        # Find the entity for our specific ticker — Marketaux can attach
        # multiple ticker entities per article (e.g. competitor mentions).
        target_entity = next(
            (e for e in entities
             if str(e.get("symbol", "")).upper() == ticker.upper()),
            None,
        )
        sentiment_score = None
        sentiment_label = None
        if target_entity:
            ss = target_entity.get("sentiment_score")
            if ss is not None:
                try:
                    sentiment_score = float(ss)
                except (TypeError, ValueError):
                    sentiment_score = None
            sentiment_label = target_entity.get("sentiment_label") or None

        rows.append({
            "title":           art.get("title", ""),
            "description":     art.get("description", ""),
            "url":             art.get("url", ""),
            "source":          art.get("source", ""),
            "published":       art.get("published_at"),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["published"] = pd.to_datetime(df["published"], utc=True, errors="coerce")
    return df.sort_values("published", ascending=False, na_position="last").reset_index(drop=True)


def is_available() -> bool:
    return bool(_api_key())
