"""
Price-comparison panel — replaces the comma-separated peers input.

Add tickers via a search field, remove with a per-ticker "✕" button,
toggle Normalized (%) vs Absolute ($), pick a time range. Underneath:
a performance-summary table (return / volatility / Sharpe / max DD).

Fetches via ``yf.download`` in a single multi-ticker call, cached in
``st.cache_data`` for 10 minutes — the user can flip view modes / time
ranges and re-render without burning quota.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, GAINS,
)

logger = logging.getLogger(__name__)


_DOWNSIDE = "rgba(184,115,51,1)"
_PERIOD_DAYS: dict[str, Optional[int]] = {
    "1M":  30,
    "3M":  90,
    "6M":  180,
    "1Y":  365,
    "2Y":  730,
    "5Y":  1825,
    "MAX": None,
}
# Color palette — primary stays gold, peers cycle through these
_PEER_COLORS = ["#10B981", "#9CA3AF", "#7DD3FC", _DOWNSIDE, "#F472B6", "#A78BFA"]


# ============================================================
# yfinance fetch — one multi-ticker call, 10-minute cache
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def _fetch_prices(tickers: tuple[str, ...], days: Optional[int]) -> pd.DataFrame:
    """Multi-ticker close-price DataFrame. Empty on every failure."""
    if not tickers:
        return pd.DataFrame()
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        if days:
            start = datetime.utcnow() - timedelta(days=days)
            data = yf.download(
                list(tickers), start=start, progress=False,
                auto_adjust=True, threads=True,
            )
        else:
            data = yf.download(
                list(tickers), period="max", progress=False,
                auto_adjust=True, threads=True,
            )
    except Exception as e:
        logger.warning(f"yf.download failed for {tickers}: {e}")
        return pd.DataFrame()
    if data is None or data.empty:
        return pd.DataFrame()
    # Single ticker → "Close" is a Series; multi → MultiIndex columns
    if isinstance(data.columns, pd.MultiIndex):
        try:
            close = data["Close"]
        except KeyError:
            return pd.DataFrame()
    else:
        # one ticker: data["Close"] is Series
        close_s = data.get("Close")
        if close_s is None:
            return pd.DataFrame()
        close = pd.DataFrame({tickers[0]: close_s})
    # Drop tickers that returned no data at all
    close = close.dropna(axis=1, how="all")
    return close.ffill().dropna(how="all")


# ============================================================
# Validation helper for the "Add ticker" path
# ============================================================
def _is_recognised_ticker(ticker: str) -> bool:
    """Quick existence check — single yfinance.info round-trip."""
    if not ticker:
        return False
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return False
    return bool(info.get("longName") or info.get("shortName"))


# ============================================================
# Performance summary table
# ============================================================
def _summary_rows(prices: pd.DataFrame, tickers: list[str]) -> list[dict]:
    rows: list[dict] = []
    for t in tickers:
        if t not in prices.columns:
            continue
        s = prices[t].dropna()
        if len(s) < 2:
            continue
        # Total return over the displayed window
        total_ret = (s.iloc[-1] / s.iloc[0] - 1.0) * 100.0
        daily = s.pct_change().dropna()
        if daily.empty:
            continue
        vol_ann = float(daily.std() * (252 ** 0.5) * 100.0)
        avg_daily_ann = float(daily.mean() * 252 * 100.0)
        rf_pct = 4.5  # rough US 10Y proxy
        sharpe = ((avg_daily_ann - rf_pct) / vol_ann) if vol_ann > 0 else float("nan")
        # Max drawdown over the period
        cum = (1.0 + daily).cumprod()
        running_max = cum.cummax()
        max_dd = float(((cum - running_max) / running_max).min() * 100.0)

        rows.append({
            "Ticker":     t,
            "Return":     f"{total_ret:+.1f}%",
            "Volatility": f"{vol_ann:.1f}%",
            "Sharpe":     ("—" if not np.isfinite(sharpe) else f"{sharpe:.2f}"),
            "Max DD":     f"{max_dd:.1f}%",
        })
    return rows


# ============================================================
# Public renderer
# ============================================================
def render_price_comparison(primary_ticker: str) -> None:
    """One-stop comparison panel for the Overview tab."""
    state_key = f"_compare_tickers_{primary_ticker}"
    if state_key not in st.session_state:
        st.session_state[state_key] = []

    st.markdown(
        '<div class="eq-section-label">PRICE COMPARISON</div>',
        unsafe_allow_html=True,
    )

    # --------- Top controls: add + period + view ---------
    c_add, c_btn, c_period = st.columns([4, 1, 1.4], gap="small")
    with c_add:
        new_ticker = st.text_input(
            "add_ticker",
            placeholder="Add ticker to compare (e.g. MSFT, NVDA, JPM)…",
            label_visibility="collapsed",
            key=f"compare_input_{primary_ticker}",
        )
    with c_btn:
        if st.button("Add", use_container_width=True,
                     key=f"compare_add_{primary_ticker}"):
            t = (new_ticker or "").upper().strip()
            if not t:
                pass
            elif t == primary_ticker.upper():
                st.warning("That's the primary ticker.")
            elif t in st.session_state[state_key]:
                st.warning(f"{t} already in the comparison.")
            else:
                if _is_recognised_ticker(t):
                    st.session_state[state_key].append(t)
                    st.rerun()
                else:
                    st.error(f"'{t}' not found in yfinance.")
    with c_period:
        time_range = st.selectbox(
            "Period", list(_PERIOD_DAYS.keys()), index=3,
            key=f"compare_period_{primary_ticker}",
            label_visibility="collapsed",
        )

    # --------- View toggle (Normalized vs Absolute) ---------
    view_mode = st.radio(
        "view_mode_compare",
        options=["Normalized (%)", "Absolute ($)"],
        horizontal=True, index=0, label_visibility="collapsed",
        key=f"compare_view_{primary_ticker}",
    )

    # --------- Active tickers chips with remove button ---------
    active_peers: list[str] = list(st.session_state[state_key])
    if active_peers:
        chip_cols = st.columns(min(6, len(active_peers)), gap="small")
        for i, tk in enumerate(active_peers):
            with chip_cols[i % len(chip_cols)]:
                if st.button(f"✕ {tk}", use_container_width=True,
                             key=f"compare_rm_{tk}_{primary_ticker}"):
                    st.session_state[state_key].remove(tk)
                    st.rerun()

    # --------- Fetch ---------
    all_tickers: tuple[str, ...] = tuple([primary_ticker] + active_peers)
    days = _PERIOD_DAYS[time_range]
    with st.spinner("Loading price history…"):
        prices = _fetch_prices(all_tickers, days)

    if prices is None or prices.empty:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            'No price history returned by yfinance for this selection.</div>',
            unsafe_allow_html=True,
        )
        return

    # --------- Pick the chart series ---------
    if view_mode == "Normalized (%)":
        # First valid value per ticker → 0%
        chart = ((prices / prices.bfill().iloc[0]) - 1.0) * 100.0
        y_title = "Total return (%)"
        hover_suffix = "%"
        y_format = "%.1f"
    else:
        chart = prices
        y_title = "Price ($)"
        hover_suffix = ""
        y_format = "%.2f"

    # --------- Plotly figure ---------
    fig = go.Figure()
    color_map: dict[str, str] = {primary_ticker: ACCENT}
    for i, tk in enumerate(active_peers):
        color_map[tk] = _PEER_COLORS[i % len(_PEER_COLORS)]

    for tk in [primary_ticker] + active_peers:
        if tk not in chart.columns:
            continue
        s = chart[tk].dropna()
        if s.empty:
            continue
        is_primary = tk == primary_ticker
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            mode="lines",
            name=tk,
            line=dict(
                color=color_map.get(tk, TEXT_SECONDARY),
                width=2.5 if is_primary else 1.5,
            ),
            hovertemplate=(
                f"<b>{tk}</b><br>%{{x|%Y-%m-%d}}<br>"
                f"%{{y:{y_format}}}{hover_suffix}<extra></extra>"
            ),
        ))

    if view_mode == "Normalized (%)":
        fig.add_hline(y=0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.5)

    fig.update_layout(
        height=400, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, zerolinecolor=BORDER),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, title=y_title,
                   zerolinecolor=BORDER),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY)),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # --------- Performance summary ---------
    if len(all_tickers) >= 1:
        rows = _summary_rows(prices, list(all_tickers))
        if rows:
            st.markdown(
                '<div class="eq-section-label" style="margin-top:10px;">'
                f'PERFORMANCE · {time_range}</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         use_container_width=True)
    st.caption(
        "Multi-ticker download cached 10 min. Sharpe uses 4.5% as a "
        "risk-free proxy. Volatility / Sharpe annualised at 252 trading days."
    )
