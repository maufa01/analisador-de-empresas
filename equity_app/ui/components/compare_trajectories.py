"""
Compare — multi-ticker trajectory overlays.

Three vertically stacked sub-sections, each rendering one to three
tickers on the same axes so the eye can compare shapes (not levels) at
a glance:

A) Margin Evolution — Gross / Operating / Net side-by-side
B) ROIC Trajectory — single chart, direct labels on last point
C) Revenue YoY % + FCF YoY % — side-by-side sub-charts

Pulls everything from already-hydrated bundles (zero FMP calls). Gaps
are NOT interpolated — a missing year shows as a break in the line so
the user doesn't read fake continuity.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis.ratios import _get, calculate_ratios, yoy_growth


_TICKER_COLORS = ["#3B82F6", "#C9A961", "#10B981"]   # blue / gold / green
_PLOT_BG       = "#131826"
_GRID          = "#1F2937"
_AXIS_TEXT     = "#6B7280"
_FONT_COLOR    = "#9CA3AF"
_WINDOW_YEARS  = 5      # cap every panel to the last N fiscal years


def _color_for(i: int) -> str:
    return _TICKER_COLORS[i % len(_TICKER_COLORS)]


def _years_axis(idx: pd.Index) -> list[int]:
    out: list[int] = []
    for d in idx:
        try:
            out.append(d.year if isinstance(d, pd.Timestamp) else int(d))
        except Exception:
            out.append(0)
    return out


def _empty_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        plot_bgcolor=_PLOT_BG, paper_bgcolor=_PLOT_BG,
        font=dict(color=_FONT_COLOR, family="Inter, sans-serif", size=11),
        height=height,
        margin=dict(l=10, r=10, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=_GRID, color=_AXIS_TEXT, tickformat="d")
    fig.update_yaxes(gridcolor=_GRID, color=_AXIS_TEXT)
    return fig


def _all_nan(series_list: list[Optional[pd.Series]]) -> bool:
    for s in series_list:
        if s is not None and not s.dropna().empty:
            return False
    return True


# ============================================================
# Sub-section A — Margin Evolution (3 panels)
# ============================================================
def _render_margins(bundles_with_ratios: list[tuple[str, pd.DataFrame]],
                    height: int) -> None:
    metrics = [
        ("Gross Margin %", "Gross Margin"),
        ("Operating Margin %", "Operating Margin"),
        ("Net Margin %", "Net Margin"),
    ]

    # Detect any metric with data across at least one ticker
    visible: list[tuple[str, str]] = []
    for col, label in metrics:
        any_data = False
        for _, ratios in bundles_with_ratios:
            if (col in ratios.columns
                    and not ratios[col].dropna().tail(_WINDOW_YEARS).empty):
                any_data = True
                break
        if any_data:
            visible.append((col, label))

    if not visible:
        st.caption("Margin data unavailable across all tickers.")
        return

    fig = make_subplots(
        rows=1, cols=len(visible),
        shared_xaxes=True,
        subplot_titles=[v[1] for v in visible],
        horizontal_spacing=0.06,
    )

    for i, (ticker, ratios) in enumerate(bundles_with_ratios):
        color = _color_for(i)
        for col_idx, (col, _) in enumerate(visible, start=1):
            if col not in ratios.columns:
                continue
            s = ratios[col].dropna().tail(_WINDOW_YEARS)
            if s.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=_years_axis(s.index), y=s.values,
                    name=ticker, mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=6),
                    legendgroup=ticker,
                    showlegend=(col_idx == 1),
                    hovertemplate=f"<b>{ticker}</b> %{{x}}: %{{y:.1f}}%<extra></extra>",
                    connectgaps=False,
                ),
                row=1, col=col_idx,
            )
        # subplot titles styling — done via annotations
    for ann in fig.layout.annotations:
        ann.font = dict(color=_FONT_COLOR, size=11)
    _empty_layout(fig, height)
    for c in range(1, len(visible) + 1):
        fig.update_yaxes(ticksuffix="%", row=1, col=c)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


# ============================================================
# Sub-section B — ROIC Trajectory
# ============================================================
def _render_roic(bundles_with_ratios: list[tuple[str, pd.DataFrame]],
                 height: int) -> None:
    series: list[tuple[str, pd.Series, str]] = []  # (ticker, series, color)
    for i, (ticker, ratios) in enumerate(bundles_with_ratios):
        if "ROIC %" not in ratios.columns:
            continue
        s = ratios["ROIC %"].dropna().tail(_WINDOW_YEARS)
        if s.empty:
            continue
        series.append((ticker, s, _color_for(i)))

    if not series:
        st.caption("ROIC data unavailable across all tickers.")
        return

    fig = go.Figure()
    for ticker, s, color in series:
        years = _years_axis(s.index)
        last_v = float(s.iloc[-1])
        fig.add_trace(go.Scatter(
            x=years, y=s.values,
            name=ticker, mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=7),
            hovertemplate=f"<b>{ticker}</b> %{{x}}: %{{y:.1f}}%<extra></extra>",
            connectgaps=False,
        ))
        # Direct label at last point
        fig.add_annotation(
            x=years[-1], y=last_v,
            text=f"<b>{ticker}</b> {last_v:.1f}%",
            showarrow=False, xshift=8, yshift=0,
            xanchor="left", font=dict(color=color, size=11),
        )

    _empty_layout(fig, height)
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


# ============================================================
# Sub-section C — Revenue YoY + FCF YoY (side-by-side)
# ============================================================
def _render_growth(bundles: dict, height: int) -> None:
    """Side-by-side YoY growth: Revenue (left) and FCF (right)."""
    rev_series: list[tuple[str, pd.Series, str]] = []
    fcf_series: list[tuple[str, pd.Series, str]] = []
    for i, (ticker, bundle) in enumerate(bundles.items()):
        color = _color_for(i)
        if not bundle or bundle.income.empty:
            continue
        rev = _get(bundle.income, "revenue")
        if rev is not None:
            g = (yoy_growth(rev).dropna() * 100.0).tail(_WINDOW_YEARS)
            if not g.empty:
                rev_series.append((ticker, g, color))
        # FCF from ratios already computed via free_cash_flow
        from analysis.ratios import free_cash_flow
        fcf = free_cash_flow(bundle.cash)
        if fcf is not None:
            gf = (yoy_growth(fcf).dropna() * 100.0).tail(_WINDOW_YEARS)
            if not gf.empty:
                fcf_series.append((ticker, gf, color))

    if not rev_series and not fcf_series:
        st.caption("Growth data unavailable across all tickers.")
        return

    titles = []
    if rev_series:
        titles.append("Revenue YoY %")
    if fcf_series:
        titles.append("FCF YoY %")
    n_cols = len(titles)

    fig = make_subplots(
        rows=1, cols=n_cols,
        shared_yaxes=False,
        subplot_titles=titles,
        horizontal_spacing=0.08,
    )

    col_idx = 1
    if rev_series:
        for ticker, s, color in rev_series:
            fig.add_trace(go.Scatter(
                x=_years_axis(s.index), y=s.values,
                name=ticker, mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=6), legendgroup=ticker,
                showlegend=True,
                hovertemplate=f"<b>{ticker}</b> %{{x}}: %{{y:+.1f}}%<extra></extra>",
                connectgaps=False,
            ), row=1, col=col_idx)
        col_idx += 1
    if fcf_series:
        for ticker, s, color in fcf_series:
            fig.add_trace(go.Scatter(
                x=_years_axis(s.index), y=s.values,
                name=ticker, mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=6), legendgroup=ticker,
                showlegend=(not rev_series),
                hovertemplate=f"<b>{ticker}</b> %{{x}}: %{{y:+.1f}}%<extra></extra>",
                connectgaps=False,
            ), row=1, col=col_idx)

    for ann in fig.layout.annotations:
        ann.font = dict(color=_FONT_COLOR, size=11)
    _empty_layout(fig, height)
    for c in range(1, n_cols + 1):
        fig.update_yaxes(ticksuffix="%", row=1, col=c)
        # Reference line at 0
        fig.add_hline(y=0, line_dash="dot",
                      line_color="rgba(156,163,175,0.4)",
                      row=1, col=c)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


# ============================================================
# Public API
# ============================================================
def render_compare_trajectories(bundles: dict, *, height: int = 280) -> None:
    """Render the 3 trajectory sub-sections. Each degrades silently when
    data is missing for all tickers in a panel."""
    if not bundles:
        st.info("No tickers loaded.")
        return

    # Pre-compute ratios once per ticker so panels reuse them
    bundles_with_ratios: list[tuple[str, pd.DataFrame]] = []
    for ticker, bundle in bundles.items():
        if bundle is None or bundle.income.empty:
            continue
        try:
            r = calculate_ratios(bundle.income, bundle.balance, bundle.cash)
        except Exception:
            r = pd.DataFrame()
        bundles_with_ratios.append((ticker, r))

    if not bundles_with_ratios:
        st.info("Trajectory needs at least one ticker with financial history.")
        return

    st.markdown('<div class="eq-section-label">MARGIN EVOLUTION</div>',
                unsafe_allow_html=True)
    _render_margins(bundles_with_ratios, height)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'ROIC TRAJECTORY</div>',
        unsafe_allow_html=True,
    )
    _render_roic(bundles_with_ratios, height)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'GROWTH YOY</div>',
        unsafe_allow_html=True,
    )
    _render_growth(bundles, height)
