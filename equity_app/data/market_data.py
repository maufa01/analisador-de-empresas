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


# Display label → yfinance ticker (kept for backwards compatibility)
INDEX_TICKERS: dict[str, str] = {
    "S&P 500":   "^GSPC",
    "NASDAQ":    "^IXIC",
    "DOW JONES": "^DJI",
    "VIX":       "^VIX",
}


# Rich index metadata for the Markets page header row. Restricted to the
# four USA benchmarks the page actually shows; international indices were
# rolled back per user feedback (the grouped pill selector felt loud).
INDEX_META: dict[str, dict[str, str]] = {
    "^GSPC":   {"name": "S&P 500",          "region": "USA"},
    "^IXIC":   {"name": "Nasdaq Composite", "region": "USA"},
    "^DJI":    {"name": "Dow Jones",        "region": "USA"},
    "^VIX":    {"name": "VIX",              "region": "USA"},
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
    Return a dict of ``{symbol: {name, region, last, change_abs, change_pct}}``
    for every index in ``INDEX_META`` (USA + Europe + Asia + LatAm).

    Tickers that yfinance can't resolve come back with None values rather
    than raising — the caller decides how to render the missing card.
    """
    yf = _yfinance()
    out: dict[str, dict] = {
        sym: {
            "name": meta["name"],
            "region": meta["region"],
            "last": None, "change_abs": None, "change_pct": None,
        }
        for sym, meta in INDEX_META.items()
    }
    if yf is None:
        return out

    tickers = list(INDEX_META.keys())
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

    for sym in tickers:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if sym not in df.columns.get_level_values(0):
                    continue
                series = df[(sym, "Close")].dropna()
            else:
                series = (df["Close"].dropna() if "Close" in df.columns
                          else df[sym].dropna())
            if len(series) < 2:
                continue
            last = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            change_abs = last - prev
            change_pct = (change_abs / prev) * 100.0 if prev else None
            out[sym].update({
                "last": last, "change_abs": change_abs, "change_pct": change_pct,
            })
        except Exception as e:
            log.warning("yf_index_parse_failed", symbol=sym, error=str(e))
            continue

    return out


# ============================================================
# Index history (generic — works for any yfinance symbol)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_index_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Daily/intraday OHLCV for any yfinance symbol over the window."""
    yf = _yfinance()
    if yf is None or not symbol:
        return pd.DataFrame()
    interval = PERIOD_TO_INTERVAL.get(period, "1d")
    try:
        df = yf.download(
            symbol, period=period, interval=interval,
            auto_adjust=False, progress=False, threads=False,
        )
    except Exception as e:
        log.warning("yf_index_history_failed",
                    symbol=symbol, period=period, error=str(e))
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# Single-ticker price history — used by the Overview tab's price chart
# and returns table on the Equity Analysis page.
@st.cache_data(ttl=300, show_spinner=False)
def get_ticker_history(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Daily OHLCV for a single ticker. Empty DataFrame on failure."""
    return get_index_history(ticker, period=period)


# Backward-compatible alias used by older pages
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
# Multi-ticker price panel — used by the Portfolio page
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_price_panel(
    tickers: tuple[str, ...] | list[str],
    *,
    period: str = "5y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Adjusted-close panel: rows = dates, columns = tickers.

    Tickers that yfinance cannot resolve are silently dropped; the caller
    sees an empty DataFrame only if EVERY ticker fails. ``tickers`` is
    accepted as a tuple to keep the cache key hashable.
    """
    yf = _yfinance()
    tickers = list(tickers)
    if yf is None or not tickers:
        return pd.DataFrame()

    try:
        df = yf.download(
            tickers,
            period=period,
            interval=interval,
            auto_adjust=True,            # we want adjusted close
            progress=False,
            group_by="ticker",
            threads=False,
        )
    except Exception as e:
        log.warning("yf_panel_download_failed",
                    tickers=tickers, period=period, error=str(e))
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
        out = df["Close"].to_frame(tickers[0]) if "Close" in df.columns else df

    return out.dropna(how="all").sort_index()


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


# ---- Internal: fetch + compute the full panel (cached separately so
#       sector/sort filters run instantly without re-hitting yfinance) ----
@st.cache_data(ttl=300, show_spinner=False)
def _fetch_movers_panel(tickers_key: tuple[str, ...]) -> pd.DataFrame:
    """
    Batch-download price + volume for ``tickers_key`` and return a single
    DataFrame with ticker / last / change_pct / beta / vol_30d / volume.

    The argument is a tuple so Streamlit can hash it; callers pass the
    universe ticker list (de-duplicated, sorted).
    """
    yf = _yfinance()
    if yf is None or not tickers_key:
        return pd.DataFrame()

    tickers = list(tickers_key)
    try:
        prices = yf.download(
            tickers + ["^GSPC"],
            period="6mo", interval="1d",
            auto_adjust=False, progress=False,
            group_by="ticker", threads=True,
        )
    except Exception as e:
        log.warning("yf_panel_movers_failed", n=len(tickers), error=str(e))
        return pd.DataFrame()
    if prices is None or prices.empty or not isinstance(prices.columns, pd.MultiIndex):
        return pd.DataFrame()

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
            beta = (_beta_vs_spx(close, spx_close)
                    if not spx_close.empty else float("nan"))
            avg_volume = (float(volume.tail(20).mean())
                          if not volume.empty else float("nan"))
            rows.append({
                "ticker": tk, "last": last, "change_pct": change_pct,
                "beta": beta, "vol_30d": vol_30d, "volume": avg_volume,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _decorate_with_meta(df: pd.DataFrame) -> pd.DataFrame:
    """Attach company name + sector + a market_cap proxy from constituents."""
    if df.empty:
        return df
    from data.constituents import META

    def _name(t: str) -> str:
        return META.get(t, {}).get("name", t)

    def _sector(t: str) -> str:
        return META.get(t, {}).get("sector", "Other")

    out = df.copy()
    out["name"] = out["ticker"].map(_name)
    out["sector"] = out["ticker"].map(_sector)
    # Market cap proxy = last price × avg-20d-volume × 200 (rough liquidity
    # ranking — real market cap requires a per-ticker .info call which we
    # avoid here for batch-fetch performance).
    out["market_cap"] = (out["last"] * out["volume"] * 200).where(
        out["volume"].notna(), other=float("nan"),
    )
    return out


@st.cache_data(ttl=300, show_spinner=False)
def get_movers(
    universe: Optional[list[str]] = None,
    *,
    sort_by: str = "gainers",
    sector: Optional[str] = None,
    top_n: int = 25,
) -> pd.DataFrame:
    """
    Top-N movers — supports universe (tickers list), optional sector
    filter, and ``sort_by`` ∈ {gainers, losers, most_active}.

    Output columns:
        ticker · name · sector · last · change_pct · beta · vol_30d ·
        volume · market_cap
    """
    yf = _yfinance()
    if yf is None:
        return pd.DataFrame()

    tickers: list[str]
    if universe is None:
        tickers = list(DEFAULT_UNIVERSE)
    else:
        tickers = list(universe)
    tickers_key = tuple(sorted(set(tickers)))

    panel = _fetch_movers_panel(tickers_key)
    if panel.empty:
        return panel

    panel = _decorate_with_meta(panel).dropna(subset=["change_pct"])
    if sector:
        panel = panel[panel["sector"] == sector]
    if panel.empty:
        return panel

    if sort_by == "gainers":
        panel = panel.sort_values("change_pct", ascending=False)
    elif sort_by == "losers":
        panel = panel.sort_values("change_pct", ascending=True)
    elif sort_by in ("most_active", "active"):
        panel = panel.sort_values("volume", ascending=False)
    return panel.head(top_n).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def get_movers_by_sector(
    universe: Optional[list[str]] = None,
    *,
    per_sector: int = 5,
    sort_by: str = "gainers",
) -> dict[str, pd.DataFrame]:
    """
    Returns ``{sector: top_N_dataframe}`` for every GICS sector with at
    least one constituent in the universe. Used by the Markets page when
    "All sectors" is selected.
    """
    from data.constituents import SECTORS

    if universe is None:
        universe = list(DEFAULT_UNIVERSE)
    panel = _fetch_movers_panel(tuple(sorted(set(universe))))
    if panel.empty:
        return {}

    panel = _decorate_with_meta(panel).dropna(subset=["change_pct"])
    out: dict[str, pd.DataFrame] = {}
    for sec in SECTORS:
        sub = panel[panel["sector"] == sec]
        if sub.empty:
            continue
        if sort_by == "gainers":
            sub = sub.sort_values("change_pct", ascending=False)
        elif sort_by == "losers":
            sub = sub.sort_values("change_pct", ascending=True)
        elif sort_by in ("most_active", "active"):
            sub = sub.sort_values("volume", ascending=False)
        out[sec] = sub.head(per_sector).reset_index(drop=True)
    return out


# ============================================================
# Sector performance — daily change of the 11 SPDR sector ETFs
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_sector_performance() -> pd.DataFrame:
    """
    Returns DataFrame with columns: sector · etf · last · change_pct ·
    market_cap (proxy = price × avg volume × 200).
    """
    from data.constituents import SECTOR_ETFS

    yf = _yfinance()
    if yf is None:
        return pd.DataFrame()

    etfs = list(SECTOR_ETFS.values())
    try:
        df = yf.download(
            etfs, period="5d", interval="1d",
            auto_adjust=False, progress=False,
            group_by="ticker", threads=True,
        )
    except Exception as e:
        log.warning("yf_sector_perf_failed", error=str(e))
        return pd.DataFrame()

    if df is None or df.empty or not isinstance(df.columns, pd.MultiIndex):
        return pd.DataFrame()

    rows: list[dict] = []
    for sector, etf in SECTOR_ETFS.items():
        try:
            close = df[(etf, "Close")].dropna()
            volume = df[(etf, "Volume")].dropna()
            if len(close) < 2:
                continue
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            change_pct = ((last / prev) - 1.0) * 100.0 if prev else float("nan")
            avg_vol = float(volume.tail(5).mean()) if not volume.empty else 0.0
            rows.append({
                "sector": sector, "etf": etf,
                "last": last, "change_pct": change_pct,
                "market_cap": last * avg_vol * 200,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


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
