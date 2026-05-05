"""
Market data fetching for the Markets page.

All functions are wrapped in st.cache_data so the page can re-render at
60s without hammering yfinance. Failures on individual tickers are
swallowed silently and logged — if EVERY ticker fails, the caller sees
empty DataFrames / None values and renders the "no data" state.
"""
from __future__ import annotations
from datetime import datetime, time, timezone
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from core.logging import get_logger

log = get_logger(__name__)


# Display label → yfinance ticker
INDEX_TICKERS: dict[str, str] = {
    "S&P 500":   "^GSPC",
    "NASDAQ":    "^IXIC",
    "DOW JONES": "^DJI",
    "VIX":       "^VIX",
}

# Default movers universe — major US large caps. Expandable.
DEFAULT_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    "BRK-B", "LLY", "JPM", "V", "WMT", "UNH", "XOM", "MA", "PG",
    "HD", "JNJ", "ORCL", "BAC", "COST", "CVX", "ABBV", "KO", "PEP",
    "CRM", "MRK", "AMD", "ADBE", "TMO", "MCD", "ACN", "CSCO", "INTC",
    "NFLX", "QCOM", "TXN", "DIS", "GE",
]

PERIOD_TO_INTERVAL: dict[str, str] = {
    "1d":  "5m",
    "5d":  "30m",
    "1mo": "1d",
    "3mo": "1d",
    "6mo": "1d",
    "1y":  "1d",
    "5y":  "1wk",
}


# ============================================================
# yfinance importer with graceful fallback
# ============================================================
def _yfinance():
    try:
        import yfinance as yf  # type: ignore
        return yf
    except ImportError:
        log.warning("yfinance_not_installed")
        return None


# ============================================================
# Indices
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_indices() -> dict[str, dict]:
    """
    Return a dict of {label: {last, change_abs, change_pct}}.

    Missing tickers come back with None values rather than raising.
    """
    yf = _yfinance()
    out: dict[str, dict] = {
        label: {"last": None, "change_abs": None, "change_pct": None}
        for label in INDEX_TICKERS
    }
    if yf is None:
        return out

    tickers = list(INDEX_TICKERS.values())
    try:
        df = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=False,
        )
    except Exception as e:
        log.warning("yf_indices_download_failed", error=str(e))
        return out

    if df is None or df.empty:
        return out

    for label, ticker in INDEX_TICKERS.items():
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if ticker not in df.columns.get_level_values(0):
                    continue
                series = df[(ticker, "Close")].dropna()
            else:
                series = df["Close"].dropna() if "Close" in df.columns else df[ticker].dropna()
            if len(series) < 2:
                continue
            last = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            change_abs = last - prev
            change_pct = (change_abs / prev) * 100.0 if prev else None
            out[label] = {"last": last, "change_abs": change_abs, "change_pct": change_pct}
        except Exception as e:
            log.warning("yf_index_parse_failed", label=label, error=str(e))
            continue

    return out


# ============================================================
# S&P 500 history
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_spx_history(period: str = "1y") -> pd.DataFrame:
    """Daily (or intraday) OHLCV for S&P 500 over the requested window."""
    yf = _yfinance()
    if yf is None:
        return pd.DataFrame()
    interval = PERIOD_TO_INTERVAL.get(period, "1d")
    try:
        df = yf.download(
            "^GSPC",
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as e:
        log.warning("yf_spx_download_failed", period=period, error=str(e))
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# ============================================================
# Top movers
# ============================================================
def _annualized_vol(close: pd.Series) -> float:
    if close is None or len(close.dropna()) < 5:
        return float("nan")
    returns = close.pct_change().dropna()
    if returns.empty:
        return float("nan")
    return float(returns.std() * np.sqrt(252) * 100.0)


def _beta_vs_spx(target: pd.Series, spx: pd.Series) -> float:
    df = pd.concat([target.pct_change(), spx.pct_change()], axis=1).dropna()
    if len(df) < 20:
        return float("nan")
    df.columns = ["t", "m"]
    cov = df.cov().iloc[0, 1]
    var_m = df["m"].var()
    if not var_m or not np.isfinite(var_m):
        return float("nan")
    return float(cov / var_m)


@st.cache_data(ttl=300, show_spinner=False)
def get_movers(
    universe: Optional[list[str]] = None,
    *,
    sort_by: str = "gainers",
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Compute movers for ``sort_by`` ∈ {gainers, losers, most_active}.

    Output columns: ticker, name, last, change_pct, beta, vol_30d, volume.
    """
    yf = _yfinance()
    if yf is None:
        return pd.DataFrame()

    tickers = universe or DEFAULT_UNIVERSE

    try:
        prices = yf.download(
            tickers + ["^GSPC"],
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=False,
        )
    except Exception as e:
        log.warning("yf_movers_download_failed", error=str(e))
        return pd.DataFrame()

    if prices is None or prices.empty:
        return pd.DataFrame()

    if not isinstance(prices.columns, pd.MultiIndex):
        return pd.DataFrame()

    # Benchmark series for beta
    try:
        spx_close = prices[("^GSPC", "Close")].dropna()
    except Exception:
        spx_close = pd.Series(dtype=float)

    rows: list[dict] = []
    for tk in tickers:
        try:
            if tk not in prices.columns.get_level_values(0):
                continue
            close = prices[(tk, "Close")].dropna()
            volume = prices[(tk, "Volume")].dropna()
            if len(close) < 2:
                continue
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            change_pct = ((last / prev) - 1.0) * 100.0 if prev else float("nan")
            vol_30d = _annualized_vol(close.tail(30))
            beta = _beta_vs_spx(close, spx_close) if not spx_close.empty else float("nan")
            avg_volume = float(volume.tail(20).mean()) if not volume.empty else float("nan")
            rows.append({
                "ticker": tk,
                "name": tk,            # name lookup deferred (avoids per-ticker .info hits)
                "last": last,
                "change_pct": change_pct,
                "beta": beta,
                "vol_30d": vol_30d,
                "volume": avg_volume,
            })
        except Exception as e:
            log.warning("yf_mover_parse_failed", ticker=tk, error=str(e))
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).dropna(subset=["change_pct"])

    if sort_by == "gainers":
        df = df.sort_values("change_pct", ascending=False)
    elif sort_by == "losers":
        df = df.sort_values("change_pct", ascending=True)
    elif sort_by in ("most_active", "active"):
        df = df.sort_values("volume", ascending=False)
    else:
        df = df.sort_values("change_pct", ascending=False)

    return df.head(top_n).reset_index(drop=True)


# ============================================================
# Market state
# ============================================================
def _now_et() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        try:
            import pytz  # type: ignore
            return datetime.now(pytz.timezone("America/New_York"))
        except Exception:
            return datetime.now()


def is_market_open() -> tuple[bool, str]:
    """Return (is_open, formatted_time_ET) for the NYSE."""
    n = _now_et()
    is_open = n.weekday() < 5 and time(9, 30) <= n.time() < time(16, 0)
    return is_open, n.strftime("%H:%M")
