"""
Data prep for stress testing.

- ``returns_matrix`` — daily returns aligned across all tickers
- ``portfolio_returns_series`` — weighted-sum portfolio return series
- ``fetch_window_prices`` — close prices for a specific historical
  date window (distinct from market_data.get_price_panel which uses
  period= form, not start/end)
- ``fetch_ticker_meta`` — sector + beta + name from yfinance.info,
  cached for 24h, with fallback to local META if yfinance fails
"""
from __future__ import annotations
from datetime import date
from typing import Mapping

import numpy as np
import pandas as pd
import streamlit as st


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


def returns_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns, dropping rows with any NaN."""
    if prices is None or prices.empty:
        return pd.DataFrame()
    return prices.pct_change().dropna(how="any")


def portfolio_returns_series(
    returns: pd.DataFrame,
    weights: Mapping[str, float],
) -> pd.Series:
    """Weighted-sum portfolio return series. Weights are normalized."""
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    cols = [t for t in weights.keys() if t in returns.columns]
    if not cols:
        return pd.Series(dtype=float)
    w = pd.Series({t: float(weights[t]) for t in cols})
    if w.sum() > 0:
        w = w / w.sum()
    return (returns[cols] * w).sum(axis=1)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_window_prices(
    tickers: tuple[str, ...],
    start: date,
    end: date,
) -> pd.DataFrame:
    """Adjusted-close panel for a specific past date window."""
    yf = _yf()
    if yf is None or not tickers:
        return pd.DataFrame()
    try:
        df = yf.download(
            list(tickers), start=start, end=end,
            progress=False, auto_adjust=True,
            group_by="ticker", threads=False,
        )
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        out = pd.DataFrame()
        for t in tickers:
            try:
                out[t] = df[(t, "Close")]
            except (KeyError, ValueError):
                continue
    else:
        if "Close" in df.columns:
            out = df["Close"].to_frame(tickers[0])
        else:
            out = df

    return out.ffill().dropna(how="all").sort_index()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def fetch_ticker_meta(ticker: str) -> dict:
    """Sector + beta + name. Falls back to local constituents META on
    yfinance failure. Beta defaults to 1.0 if missing or non-numeric."""
    out: dict = {"ticker": ticker, "sector": None, "beta": 1.0, "name": ticker}
    yf = _yf()
    if yf is not None:
        try:
            info = yf.Ticker(ticker).info or {}
            sec = info.get("sector")
            if sec:
                out["sector"] = sec
            beta = info.get("beta")
            try:
                if beta is not None and np.isfinite(float(beta)):
                    out["beta"] = float(beta)
            except (TypeError, ValueError):
                pass
            name = info.get("shortName") or info.get("longName")
            if name:
                out["name"] = name
        except Exception:
            pass
    if out["sector"] is None:
        try:
            from data.constituents import sector_of
            s = sector_of(ticker)
            if s:
                out["sector"] = s
        except Exception:
            pass
    if out["sector"] is None:
        out["sector"] = "Unknown"
    return out
