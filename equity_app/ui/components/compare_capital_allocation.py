"""
Compare — Cumulative capital allocation (5y).

Two stacked-bar charts side-by-side:
  Left  — absolute $B per bucket (CapEx, Buybacks, Dividends, M&A)
  Right — same buckets normalized to 100% (relative mix)

Annotations above each absolute bar show cumulative FCF over the same
period — useful for spotting "returned more than they generated" cases.

Acquisition data is best-effort: many SEC filings lump M&A into
"investingCashFlow" rather than breaking it out. If acquisitionsNet is
unavailable for ALL tickers, the M&A bucket is silently dropped.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis.ratios import _get, free_cash_flow


_PLOT_BG    = "#131826"
_GRID       = "#1F2937"
_AXIS_TEXT  = "#6B7280"
_FONT_COLOR = "#9CA3AF"

# Buyside-style colours per bucket
_BUCKET_COLORS = {
    "Reinvestment": "#3B82F6",   # blue
    "Buybacks":     "#C9A961",   # gold
    "Dividends":    "#10B981",   # green
    "M&A":          "#8B5C2C",   # copper
}


def _abs_sum(s: Optional[pd.Series], years: int = 5) -> Optional[float]:
    if s is None:
        return None
    cut = s.dropna().tail(years)
    if cut.empty:
        return None
    return float(cut.abs().sum())


def _sum_signed(s: Optional[pd.Series], years: int = 5) -> Optional[float]:
    if s is None:
        return None
    cut = s.dropna().tail(years)
    if cut.empty:
        return None
    return float(cut.sum())


def _bucket_totals(bundle, years: int = 5) -> dict[str, Optional[float]]:
    capex     = _get(bundle.cash, "capex")
    buybacks  = _get(bundle.cash, "buybacks")
    dividends = _get(bundle.cash, "dividends_paid")

    acquisitions: Optional[pd.Series] = None
    if not bundle.cash.empty and "acquisitionsNet" in bundle.cash.columns:
        try:
            acquisitions = bundle.cash["acquisitionsNet"].astype(float)
        except Exception:
            acquisitions = None

    return {
        "Reinvestment": _abs_sum(capex, years),
        "Buybacks":     _abs_sum(buybacks, years),
        "Dividends":    _abs_sum(dividends, years),
        "M&A":          _abs_sum(acquisitions, years),
    }


def _fcf_total(bundle, years: int = 5) -> Optional[float]:
    fcf = free_cash_flow(bundle.cash)
    return _sum_signed(fcf, years)


def render_compare_capital_allocation(bundles: dict, years: int = 5) -> None:
    if not bundles:
        st.info("Capital allocation needs at least one ticker.")
        return

    tickers: list[str] = []
    totals: dict[str, dict[str, Optional[float]]] = {}
    fcf_totals: dict[str, Optional[float]] = {}

    for t, b in bundles.items():
        if b is None or b.cash.empty:
            continue
        tickers.append(t)
        totals[t] = _bucket_totals(b, years=years)
        fcf_totals[t] = _fcf_total(b, years=years)

    if not tickers:
        st.info("No cash flow data available for capital allocation.")
        return

    # Drop M&A bucket if missing for every ticker
    buckets = ["Reinvestment", "Buybacks", "Dividends", "M&A"]
    visible_buckets = [b for b in buckets
                        if any(totals[t].get(b) is not None for t in tickers)]
    if not visible_buckets:
        st.info("No bucket data available for any ticker.")
        return

    # Build the matrix (ticker × bucket), filling None as 0 for stacking
    abs_matrix: dict[str, list[float]] = {b: [] for b in visible_buckets}
    for t in tickers:
        for b in visible_buckets:
            v = totals[t].get(b)
            abs_matrix[b].append(float(v) if v is not None else 0.0)

    # Normalized (% of total per ticker)
    norm_matrix: dict[str, list[float]] = {b: [] for b in visible_buckets}
    for i, t in enumerate(tickers):
        total_t = sum(abs_matrix[b][i] for b in visible_buckets)
        for b in visible_buckets:
            v = abs_matrix[b][i]
            norm_matrix[b].append((v / total_t * 100.0) if total_t > 0 else 0.0)

    # Two charts side by side
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Cumulative 5y ($B)", "Mix (%)"),
        horizontal_spacing=0.10,
    )

    # ---- Absolute stacked bars (col 1) ----
    for b in visible_buckets:
        y_vals = [v / 1e9 for v in abs_matrix[b]]
        fig.add_trace(go.Bar(
            x=tickers, y=y_vals,
            name=b, marker_color=_BUCKET_COLORS.get(b, "#9CA3AF"),
            legendgroup=b, showlegend=True,
            hovertemplate=f"<b>%{{x}}</b><br>{b}: $%{{y:.1f}}B<extra></extra>",
        ), row=1, col=1)

    # FCF annotations above each absolute bar
    abs_totals_per_ticker = [
        sum(abs_matrix[b][i] for b in visible_buckets)
        for i, _ in enumerate(tickers)
    ]
    for i, t in enumerate(tickers):
        fcf_v = fcf_totals.get(t)
        if fcf_v is None or not np.isfinite(fcf_v):
            continue
        top_y = abs_totals_per_ticker[i] / 1e9
        fig.add_annotation(
            x=t, y=top_y,
            text=f"<b>FCF: ${fcf_v/1e9:+.1f}B</b>",
            showarrow=False, yshift=15,
            font=dict(color=_FONT_COLOR, size=10),
            xref="x1", yref="y1",
        )

    # ---- Normalized stacked bars (col 2) ----
    for b in visible_buckets:
        fig.add_trace(go.Bar(
            x=tickers, y=norm_matrix[b],
            name=b, marker_color=_BUCKET_COLORS.get(b, "#9CA3AF"),
            legendgroup=b, showlegend=False,
            hovertemplate=f"<b>%{{x}}</b><br>{b}: %{{y:.1f}}%<extra></extra>",
        ), row=1, col=2)

    fig.update_layout(
        barmode="stack",
        plot_bgcolor=_PLOT_BG, paper_bgcolor=_PLOT_BG,
        font=dict(color=_FONT_COLOR, family="Inter, sans-serif", size=11),
        height=380,
        margin=dict(l=10, r=10, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=_GRID, color=_AXIS_TEXT)
    fig.update_yaxes(gridcolor=_GRID, color=_AXIS_TEXT, row=1, col=1,
                     ticksuffix="B")
    fig.update_yaxes(gridcolor=_GRID, color=_AXIS_TEXT, row=1, col=2,
                     ticksuffix="%", range=[0, 100])
    for ann in fig.layout.annotations[:2]:    # only the subplot titles
        if hasattr(ann, "font"):
            ann.font = dict(color=_FONT_COLOR, size=11)

    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    note = ("Buckets are cumulative ABSOLUTE values over the last 5 fiscal "
            "years (signs ignored — both inflows and outflows count toward "
            "the magnitude). FCF annotation above each absolute bar is "
            "signed (cumulative). Mix chart normalizes each ticker's "
            "buckets to 100%.")
    if "M&A" not in visible_buckets:
        note += (" M&A bucket omitted: acquisitionsNet not reported for "
                  "any selected ticker.")
    st.caption(note)
