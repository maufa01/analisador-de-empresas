"""
Watchlist alert evaluator — runs five checks per ticker:

    target_hit       price ≥ target_price
    stop_loss        price ≤ stop_loss
    score_change     |new_score − last_score| ≥ 15
    earnings_near    days_to_next_earnings ∈ {30, 14, 7, 1}
    sentiment_drop   7-day sentiment Δ ≤ −0.30

This module is intentionally yfinance-only — no FMP, no FRED, no
Anthropic. Each check tolerates an empty / failed sub-fetch so a single
flaky ticker doesn't crash the loop.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import logging
import pandas as pd

from data.watchlist_alerts_db import (
    get_meta, record_event, update_last_check,
)
from data.watchlist_db import list_watchlist

logger = logging.getLogger(__name__)


@dataclass
class TriggeredAlert:
    ticker: str
    kind: str
    message: str


# ============================================================
# yfinance helpers
# ============================================================
def _current_price(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        price = info.get("last_price") if hasattr(info, "get") else None
        if price:
            return float(price)
        # Older yfinance versions
        price = yf.Ticker(ticker).info.get("currentPrice")
        return float(price) if price else None
    except Exception:
        return None


def _next_earnings_days(ticker: str) -> Optional[int]:
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
    except Exception:
        return None
    if cal is None:
        return None
    raw_date = None
    if isinstance(cal, dict):
        raw_date = cal.get("Earnings Date")
    elif hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
        try:
            raw_date = cal.loc["Earnings Date"].iloc[0]
        except Exception:
            return None
    if raw_date is None:
        return None
    if isinstance(raw_date, list) and raw_date:
        raw_date = raw_date[0]
    try:
        ts = pd.to_datetime(raw_date)
        return int((ts - pd.Timestamp.now()).days)
    except Exception:
        return None


# ============================================================
# Single-ticker check
# ============================================================
def check_ticker(
    ticker: str, *,
    new_score: Optional[int] = None, new_rating: Optional[str] = None,
) -> list[TriggeredAlert]:
    """Run every check for one ticker. ``new_score``/``new_rating`` come from
    the caller's pipeline — pass them so we can record the change."""
    triggered: list[TriggeredAlert] = []
    meta = get_meta(ticker)
    if not meta:
        # Auto-create empty meta row so last-check still gets stored
        update_last_check(ticker, score=new_score, rating=new_rating)
        meta = get_meta(ticker)

    price = _current_price(ticker)

    # 1 — target hit
    target = meta.get("target_price")
    if price is not None and target and price >= target:
        msg = f"{ticker} hit target — current ${price:.2f} ≥ target ${target:.2f}"
        record_event(ticker, "target_hit", msg,
                     {"price": price, "target": target})
        triggered.append(TriggeredAlert(ticker, "target_hit", msg))

    # 2 — stop loss
    stop = meta.get("stop_loss")
    if price is not None and stop and price <= stop:
        msg = f"{ticker} STOP LOSS — current ${price:.2f} ≤ stop ${stop:.2f}"
        record_event(ticker, "stop_loss", msg,
                     {"price": price, "stop": stop})
        triggered.append(TriggeredAlert(ticker, "stop_loss", msg))

    # 3 — score change
    last_score = meta.get("last_score")
    if new_score is not None and last_score is not None:
        delta = new_score - last_score
        if abs(delta) >= 15:
            direction = "improved" if delta > 0 else "deteriorated"
            msg = f"{ticker} score {direction}: {last_score} → {new_score}"
            record_event(ticker, "score_change", msg,
                         {"old": last_score, "new": new_score, "delta": delta})
            triggered.append(TriggeredAlert(ticker, "score_change", msg))

    # 4 — earnings approaching
    days = _next_earnings_days(ticker)
    if days is not None and 0 <= days and days in (30, 14, 7, 1):
        msg = f"{ticker} earnings in {days} day{'s' if days != 1 else ''}"
        record_event(ticker, "earnings_near", msg, {"days": days})
        triggered.append(TriggeredAlert(ticker, "earnings_near", msg))

    # 5 — sentiment drop (lazy import to avoid spinning VADER on cold start)
    try:
        from analysis.news_sentiment import analyze_ticker_news
        ns = analyze_ticker_news(ticker, limit=20, engine="vader")
        change = ns.sentiment_change_7d
        if change is not None and change <= -0.30:
            msg = (f"{ticker} sentiment dropped sharply: "
                   f"{change:+.2f} over 7d")
            record_event(ticker, "sentiment_drop", msg, {"delta": change})
            triggered.append(TriggeredAlert(ticker, "sentiment_drop", msg))
    except Exception as e:
        logger.debug(f"sentiment check skipped for {ticker}: {e}")

    # Persist the latest score/rating regardless of triggers
    if new_score is not None or new_rating is not None:
        update_last_check(ticker, score=new_score, rating=new_rating)

    return triggered


# ============================================================
# Run for the entire watchlist
# ============================================================
def check_all() -> list[TriggeredAlert]:
    """Loops over the watchlist and runs every check. No score is computed
    here — score updates happen at analysis time in the page itself."""
    out: list[TriggeredAlert] = []
    for tk in list_watchlist():
        try:
            out.extend(check_ticker(tk))
        except Exception as e:
            logger.warning(f"alert check failed for {tk}: {e}")
            continue
    return out
