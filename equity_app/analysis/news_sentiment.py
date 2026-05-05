"""
News + sentiment via yfinance + VADER (default) or FinBERT (opt-in).

Why VADER first: zero cold-start cost (~1ms init, no model download),
solid enough for headline-level sentiment. FinBERT is finance-tuned and
more accurate but pulls a 440MB model on first use — wire it behind a
flag so Streamlit Cloud users don't pay that cost on every reboot.

Public API:
    fetch_news(ticker, limit=30)            → DataFrame
    score_sentiment(texts, *, engine="vader" | "finbert")
                                            → DataFrame
    analyze_ticker_news(ticker, ...)        → NewsSentimentResult

Limitations: yfinance returns ~10 items per ticker and only headlines.
For 30+ items + body text, wire Alpha Vantage / Marketaux later.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# Result
# ============================================================
@dataclass
class NewsSentimentResult:
    available: bool
    n_items: int = 0
    overall_score: Optional[float] = None       # [-1, +1]
    overall_label: str = "—"
    flag: str = "unknown"                       # green / yellow / red
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    sentiment_change_7d: Optional[float] = None
    volume_spike: bool = False
    engine: str = "vader"
    note: str = ""

    items: pd.DataFrame = field(default_factory=pd.DataFrame)


# ============================================================
# Fetch — yfinance
# ============================================================
def fetch_news(ticker: str, limit: int = 30) -> pd.DataFrame:
    """Pull headlines from yfinance.Ticker.news. Returns empty DF on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    try:
        raw = yf.Ticker(ticker).news or []
    except Exception as e:
        logger.warning(f"yfinance news fetch failed for {ticker}: {e}")
        return pd.DataFrame()

    if not raw:
        return pd.DataFrame()

    items = []
    for it in raw[:limit]:
        # yfinance ~v0.2.40+ wraps the payload in `content`; older versions are flat.
        c = it.get("content") if isinstance(it, dict) else None
        if isinstance(c, dict):
            title = c.get("title", "")
            provider = c.get("provider")
            publisher = (provider or {}).get("displayName", "") if isinstance(provider, dict) else ""
            canonical = c.get("canonicalUrl")
            link = (canonical or {}).get("url", "") if isinstance(canonical, dict) else ""
            published_raw = c.get("pubDate") or c.get("displayTime")
            try:
                published = pd.to_datetime(published_raw, utc=True)
            except Exception:
                published = pd.NaT
        else:
            title = it.get("title", "")
            publisher = it.get("publisher", "")
            link = it.get("link", "")
            ts = it.get("providerPublishTime")
            try:
                published = pd.to_datetime(ts, unit="s", utc=True) if ts else pd.NaT
            except Exception:
                published = pd.NaT

        if not title:
            continue
        items.append({
            "title": title,
            "publisher": publisher,
            "link": link,
            "published": published,
        })

    df = pd.DataFrame(items)
    if df.empty:
        return df
    df = df.sort_values("published", ascending=False, na_position="last")
    return df.reset_index(drop=True)


# ============================================================
# Sentiment engines
# ============================================================
def _score_vader(texts: list[str]) -> pd.DataFrame:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        return pd.DataFrame([{"text": t, "label": "neutral", "value": 0.0}
                             for t in texts])

    sia = SentimentIntensityAnalyzer()
    rows = []
    for t in texts:
        try:
            comp = sia.polarity_scores(t)["compound"]
        except Exception:
            comp = 0.0
        if comp >= 0.05:
            label = "positive"
        elif comp <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        rows.append({"text": t, "label": label, "value": float(comp)})
    return pd.DataFrame(rows)


_FINBERT_PIPE = None


def _get_finbert():
    """Lazy load — caches across calls within the same process."""
    global _FINBERT_PIPE
    if _FINBERT_PIPE is None:
        try:
            from transformers import pipeline  # type: ignore
            _FINBERT_PIPE = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                device=-1,
            )
        except Exception as e:
            logger.warning(f"FinBERT unavailable, falling back to VADER: {e}")
            _FINBERT_PIPE = "unavailable"
    return _FINBERT_PIPE


def _score_finbert(texts: list[str]) -> pd.DataFrame:
    pipe = _get_finbert()
    if pipe == "unavailable":
        return _score_vader(texts)

    rows = []
    for i in range(0, len(texts), 16):
        batch = texts[i:i + 16]
        try:
            preds = pipe(batch, truncation=True, max_length=512)
        except Exception as e:
            logger.warning(f"FinBERT batch failed: {e}")
            for t in batch:
                rows.append({"text": t, "label": "neutral", "value": 0.0})
            continue
        for t, p in zip(batch, preds):
            label = p["label"].lower()
            conf = float(p["score"])
            if label == "positive":
                value = conf
            elif label == "negative":
                value = -conf
            else:
                value = 0.0
            rows.append({"text": t, "label": label, "value": value})
    return pd.DataFrame(rows)


def score_sentiment(texts: list[str], *, engine: str = "vader") -> pd.DataFrame:
    """Engine = 'vader' (default, fast) or 'finbert' (heavy, accurate)."""
    if not texts:
        return pd.DataFrame(columns=["text", "label", "value"])
    if engine == "finbert":
        return _score_finbert(texts)
    return _score_vader(texts)


# ============================================================
# High-level analyzer
# ============================================================
def _value_to_label(v: float) -> str:
    if v > 0.3: return "Very Positive"
    if v > 0.1: return "Positive"
    if v > -0.1: return "Neutral"
    if v > -0.3: return "Negative"
    return "Very Negative"


def _value_to_flag(v: float) -> str:
    if v > 0.1: return "green"
    if v > -0.1: return "yellow"
    return "red"


def analyze_ticker_news(
    ticker: str, *, limit: int = 30, engine: str = "vader",
) -> NewsSentimentResult:
    df = fetch_news(ticker, limit=limit)
    if df.empty:
        return NewsSentimentResult(
            available=False,
            note="No news returned by yfinance for this ticker.",
        )

    scored = score_sentiment(df["title"].tolist(), engine=engine)
    df = df.copy()
    df["sentiment_label"] = scored["label"].values
    df["sentiment_value"] = scored["value"].values

    overall = float(df["sentiment_value"].mean())

    pos = int((df["sentiment_value"] > 0.1).sum())
    neg = int((df["sentiment_value"] < -0.1).sum())
    neu = int(len(df) - pos - neg)

    # 7-day trend
    change_7d: Optional[float] = None
    pub = df["published"].dropna()
    if not pub.empty:
        now = pd.Timestamp.now(tz="UTC")
        cut_recent = now - pd.Timedelta(days=7)
        cut_prev = now - pd.Timedelta(days=14)
        recent = df[df["published"] >= cut_recent]
        previous = df[(df["published"] >= cut_prev) & (df["published"] < cut_recent)]
        if not recent.empty and not previous.empty:
            change_7d = float(recent["sentiment_value"].mean()
                              - previous["sentiment_value"].mean())

    # Volume spike
    spike = False
    if not pub.empty:
        daily = df.dropna(subset=["published"]).groupby(
            df["published"].dt.date
        ).size()
        if len(daily) >= 3:
            avg = float(daily.mean())
            top = int(daily.max())
            spike = bool(top > avg * 2.5 and top >= 3)

    return NewsSentimentResult(
        available=True,
        n_items=len(df),
        overall_score=overall,
        overall_label=_value_to_label(overall),
        flag=_value_to_flag(overall),
        positive_count=pos,
        neutral_count=neu,
        negative_count=neg,
        sentiment_change_7d=change_7d,
        volume_spike=spike,
        engine=engine,
        items=df,
        note=("Headlines only (yfinance) — for body-text sentiment + 50+ "
              "items wire Alpha Vantage / Marketaux."),
    )
