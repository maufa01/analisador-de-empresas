"""
Compare — pair-trade multiples spread (only when N == 2).

For a chosen pair (TKR_A, TKR_B), computes the monthly ratio of three
valuation multiples — P/E, EV/EBITDA, P/FCF — over 5 years, plus the
z-score of the current ratio against its 5-year mean.

Read as: "AAPL has historically traded at 1.30× MSFT on P/E. Today
1.61× → +2.1σ above 5y mean." Useful for relative-value entry timing
when you've already decided both businesses are buyable.

Data sources:
- Bundle's income / balance / cash for fundamentals (annual)
- yfinance month-end prices for the price series (5y, cached upstream)
- Reporting lag of ~90 days from fiscal year end before the new
  fundamentals become "available" to the market
"""
from __future__ import annotations
from typing import Optional

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.ratios import _get, free_cash_flow


_PLOT_BG    = "#131826"
_GRID       = "#1F2937"
_AXIS_TEXT  = "#6B7280"
_FONT_COLOR = "#9CA3AF"

_TICKER_COLORS = {"A": "#3B82F6", "B": "#C9A961"}
_RATIO_COLOR = "#E5E7EB"
_REF_COLOR   = "rgba(156,163,175,0.6)"
_BAND_COLOR  = "rgba(156,163,175,0.25)"
_LAG_DAYS    = 90


# ============================================================
# Helpers
# ============================================================
def _monthly_close(prices: pd.DataFrame) -> pd.Series:
    """Resample to month-end close. `prices` is the yfinance hist DF
    with a "Close" column."""
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    col = "Close" if "Close" in prices.columns else prices.columns[0]
    s = prices[col].dropna()
    if s.empty:
        return s
    # Drop tz so the index aligns cleanly with fundamentals
    try:
        s.index = s.index.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    # Pandas ≥2.2 deprecated "M"; "ME" (month-end) is the new alias.
    try:
        return s.resample("ME").last().dropna()
    except ValueError:
        return s.resample("M").last().dropna()


def _as_of(annual_series: Optional[pd.Series],
            ts: pd.Timestamp, lag_days: int = _LAG_DAYS) -> Optional[float]:
    """Most recent annual value reported AT LEAST `lag_days` BEFORE `ts`."""
    if annual_series is None or annual_series.empty:
        return None
    s = annual_series.dropna()
    cutoff = ts - pd.Timedelta(days=lag_days)
    visible = s.loc[s.index <= cutoff]
    if visible.empty:
        return None
    v = float(visible.iloc[-1])
    return v if np.isfinite(v) else None


def _series_as_of(annual: Optional[pd.Series],
                   month_index: pd.DatetimeIndex,
                   lag_days: int = _LAG_DAYS) -> pd.Series:
    """For each month-end timestamp, return the latest annual value as
    of that month (or NaN)."""
    if annual is None or annual.empty:
        return pd.Series(np.nan, index=month_index)
    s = annual.dropna()
    # Make sure both indices are tz-naive
    try:
        s.index = s.index.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    out = []
    for ts in month_index:
        v = _as_of(s, ts, lag_days=lag_days)
        out.append(np.nan if v is None else v)
    return pd.Series(out, index=month_index, dtype=float)


def _diluted_shares(bundle) -> Optional[pd.Series]:
    """Best-effort diluted share count series."""
    for key in ("weighted_avg_shares",):
        s = _get(bundle.income, key)
        if s is not None and not s.dropna().empty:
            return s
    if "shares_diluted" in bundle.income.columns:
        try:
            return bundle.income["shares_diluted"].astype(float)
        except Exception:
            pass
    return None


def _ebitda_series(bundle) -> Optional[pd.Series]:
    ebitda = _get(bundle.income, "ebitda")
    if ebitda is not None and not ebitda.dropna().empty:
        return ebitda
    # Reconstruct EBIT + D&A. Note: `or` triggers __bool__ on a Series
    # which raises "truth value ambiguous" — explicit None check instead.
    ebit = _get(bundle.income, "ebit")
    da = _get(bundle.cash, "depreciation_cf")
    if da is None:
        da = _get(bundle.income, "depreciation_inc")
    if ebit is None or da is None:
        return None
    common = ebit.index.intersection(da.index)
    if len(common) == 0:
        return None
    return (ebit.loc[common].add(da.loc[common], fill_value=0.0)).dropna()


def _net_debt_series(bundle) -> Optional[pd.Series]:
    debt = _get(bundle.balance, "total_debt")
    if debt is None:
        ltd = _get(bundle.balance, "long_term_debt")
        std = _get(bundle.balance, "short_term_debt")
        if ltd is None and std is None:
            return None
        if ltd is None:
            debt = std
        elif std is None:
            debt = ltd
        else:
            debt = ltd.add(std, fill_value=0.0)
    cash_eq = _get(bundle.balance, "cash_eq")
    if cash_eq is None:
        return debt
    common = debt.index.intersection(cash_eq.index)
    if len(common) == 0:
        return debt
    return (debt.loc[common] - cash_eq.loc[common]).dropna()


def _eps_series(bundle) -> Optional[pd.Series]:
    """Reported diluted EPS series."""
    for key in ("eps_diluted", "eps"):
        s = _get(bundle.income, key)
        if s is not None and not s.dropna().empty:
            return s
    return None


def _fcf_per_share_series(bundle) -> Optional[pd.Series]:
    fcf = free_cash_flow(bundle.cash)
    shares = _diluted_shares(bundle)
    if fcf is None or shares is None:
        return None
    common = fcf.index.intersection(shares.index)
    if len(common) == 0:
        return None
    return (fcf.loc[common] / shares.loc[common]).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()


def _pe_series(bundle, prices_m: pd.Series) -> pd.Series:
    eps = _eps_series(bundle)
    eps_aligned = _series_as_of(eps, prices_m.index)
    return (prices_m / eps_aligned).replace([np.inf, -np.inf], np.nan)


def _ev_ebitda_series(bundle, prices_m: pd.Series) -> pd.Series:
    """EV/EBITDA = (mcap + net_debt) / EBITDA."""
    shares = _diluted_shares(bundle)
    ebitda = _ebitda_series(bundle)
    nd = _net_debt_series(bundle)
    if shares is None or ebitda is None:
        return pd.Series(np.nan, index=prices_m.index)
    shares_aligned = _series_as_of(shares, prices_m.index)
    ebitda_aligned = _series_as_of(ebitda, prices_m.index)
    nd_aligned = (_series_as_of(nd, prices_m.index)
                  if nd is not None else pd.Series(0.0, index=prices_m.index))
    mcap = prices_m * shares_aligned
    ev = mcap + nd_aligned.fillna(0.0)
    return (ev / ebitda_aligned).replace([np.inf, -np.inf], np.nan)


def _pfcf_series(bundle, prices_m: pd.Series) -> pd.Series:
    fcfps = _fcf_per_share_series(bundle)
    fcfps_aligned = _series_as_of(fcfps, prices_m.index)
    return (prices_m / fcfps_aligned).replace([np.inf, -np.inf], np.nan)


# ============================================================
# Chart for one multiple tab
# ============================================================
def _render_multiple_tab(*, label: str,
                         a_ticker: str, b_ticker: str,
                         m_a: pd.Series, m_b: pd.Series) -> None:
    # Drop rows where either side is missing/non-positive
    both = pd.concat([m_a, m_b], axis=1, keys=[a_ticker, b_ticker])
    both = both.replace([np.inf, -np.inf], np.nan).dropna()
    both = both[(both[a_ticker] > 0) & (both[b_ticker] > 0)]

    if len(both) < 12:
        st.caption(
            f"Insufficient overlapping {label} history (need ≥12 monthly "
            f"observations, got {len(both)})."
        )
        return

    ratio = both[a_ticker] / both[b_ticker]
    mean_r = float(ratio.mean())
    std_r = float(ratio.std(ddof=0))
    last_r = float(ratio.iloc[-1])
    z = (last_r - mean_r) / std_r if std_r > 0 else 0.0

    # ---- Top: ratio chart with mean / ±1σ / ±2σ bands ----
    fig_top = go.Figure()
    fig_top.add_trace(go.Scatter(
        x=ratio.index, y=ratio.values,
        mode="lines", name=f"{a_ticker}/{b_ticker} {label}",
        line=dict(color=_RATIO_COLOR, width=2),
        hovertemplate="<b>%{x|%Y-%m}</b>: %{y:.2f}x<extra></extra>",
    ))
    if std_r > 0:
        # Shaded ±1σ band
        upper1 = mean_r + std_r
        lower1 = mean_r - std_r
        fig_top.add_hrect(y0=lower1, y1=upper1,
                          fillcolor="rgba(156,163,175,0.10)",
                          line_width=0)
        fig_top.add_hline(y=mean_r, line_color=_REF_COLOR,
                          line_dash="solid", line_width=1,
                          annotation_text=f"μ {mean_r:.2f}",
                          annotation_position="right",
                          annotation_font=dict(color=_AXIS_TEXT, size=10))
        fig_top.add_hline(y=mean_r + 2 * std_r, line_color=_BAND_COLOR,
                          line_dash="dot", line_width=1,
                          annotation_text="+2σ",
                          annotation_position="right",
                          annotation_font=dict(color=_AXIS_TEXT, size=10))
        fig_top.add_hline(y=mean_r - 2 * std_r, line_color=_BAND_COLOR,
                          line_dash="dot", line_width=1,
                          annotation_text="−2σ",
                          annotation_position="right",
                          annotation_font=dict(color=_AXIS_TEXT, size=10))
    fig_top.update_layout(
        plot_bgcolor=_PLOT_BG, paper_bgcolor=_PLOT_BG,
        font=dict(color=_FONT_COLOR, family="Inter, sans-serif", size=11),
        height=240, margin=dict(l=10, r=50, t=10, b=10),
        showlegend=False,
    )
    fig_top.update_xaxes(gridcolor=_GRID, color=_AXIS_TEXT)
    fig_top.update_yaxes(gridcolor=_GRID, color=_AXIS_TEXT, ticksuffix="x")
    st.plotly_chart(fig_top, use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Middle: each multiple line by ticker ----
    fig_mid = go.Figure()
    fig_mid.add_trace(go.Scatter(
        x=both.index, y=both[a_ticker].values,
        name=a_ticker, mode="lines",
        line=dict(color=_TICKER_COLORS["A"], width=2),
        hovertemplate=f"<b>{a_ticker}</b> %{{x|%Y-%m}}: %{{y:.1f}}x<extra></extra>",
    ))
    fig_mid.add_trace(go.Scatter(
        x=both.index, y=both[b_ticker].values,
        name=b_ticker, mode="lines",
        line=dict(color=_TICKER_COLORS["B"], width=2),
        hovertemplate=f"<b>{b_ticker}</b> %{{x|%Y-%m}}: %{{y:.1f}}x<extra></extra>",
    ))
    fig_mid.update_layout(
        plot_bgcolor=_PLOT_BG, paper_bgcolor=_PLOT_BG,
        font=dict(color=_FONT_COLOR, family="Inter, sans-serif", size=11),
        height=200, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig_mid.update_xaxes(gridcolor=_GRID, color=_AXIS_TEXT)
    fig_mid.update_yaxes(gridcolor=_GRID, color=_AXIS_TEXT, ticksuffix="x")
    st.plotly_chart(fig_mid, use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Bottom: textual annotation ----
    direction = "above" if z >= 0 else "below"
    color = ("#B87333" if abs(z) >= 2.0
             else "#C9A961" if abs(z) >= 1.0
             else "#10B981")
    text = (
        f'<b>{a_ticker}</b> historically trades at <b>{mean_r:.2f}x</b> '
        f'<b>{b_ticker}</b> in {label}. Today <b>{last_r:.2f}x</b> → '
        f'<span style="color:{color}; font-weight:600;">{z:+.1f}σ</span> '
        f'{direction} 5y mean.'
    )
    st.markdown(
        f'<div style="color:#9CA3AF; font-size:12px; line-height:1.6; '
        f'margin-top:4px;">{text}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Public API
# ============================================================
def render_multiples_spread(bundles: dict, prices_hist: dict) -> None:
    """Render the pair-trade spread chart. Bails out gracefully if the
    bundles dict isn't exactly 2 tickers."""
    tickers = list(bundles.keys())
    if len(tickers) != 2:
        st.info("Pair-trade spread requires exactly 2 tickers.")
        return

    a_ticker, b_ticker = tickers
    a_bundle, b_bundle = bundles[a_ticker], bundles[b_ticker]
    if a_bundle is None or b_bundle is None:
        st.info("Both tickers need hydrated bundles.")
        return

    a_prices_raw = prices_hist.get(a_ticker)
    b_prices_raw = prices_hist.get(b_ticker)
    a_m = _monthly_close(a_prices_raw)
    b_m = _monthly_close(b_prices_raw)
    if a_m.empty or b_m.empty:
        st.info("Insufficient 5y price history for one or both tickers.")
        return

    # Align month-end indices
    common = a_m.index.intersection(b_m.index)
    if len(common) < 12:
        st.info(
            f"Need ≥12 overlapping monthly observations (got {len(common)})."
        )
        return
    a_m = a_m.loc[common]
    b_m = b_m.loc[common]

    pe_a    = _pe_series(a_bundle, a_m)
    pe_b    = _pe_series(b_bundle, b_m)
    ev_a    = _ev_ebitda_series(a_bundle, a_m)
    ev_b    = _ev_ebitda_series(b_bundle, b_m)
    pfcf_a  = _pfcf_series(a_bundle, a_m)
    pfcf_b  = _pfcf_series(b_bundle, b_m)

    tab_pe, tab_ev, tab_pfcf = st.tabs(["P/E", "EV/EBITDA", "P/FCF"])
    with tab_pe:
        _render_multiple_tab(
            label="P/E",
            a_ticker=a_ticker, b_ticker=b_ticker,
            m_a=pe_a, m_b=pe_b,
        )
    with tab_ev:
        _render_multiple_tab(
            label="EV/EBITDA",
            a_ticker=a_ticker, b_ticker=b_ticker,
            m_a=ev_a, m_b=ev_b,
        )
    with tab_pfcf:
        _render_multiple_tab(
            label="P/FCF",
            a_ticker=a_ticker, b_ticker=b_ticker,
            m_a=pfcf_a, m_b=pfcf_b,
        )

    st.caption(
        "Monthly P/E uses the most recent reported diluted EPS available "
        "as of each month-end (assuming a 90-day reporting lag). EV/EBITDA "
        "uses month-end market cap plus net debt over reported EBITDA. "
        "P/FCF uses month-end price over FCF per diluted share."
    )
