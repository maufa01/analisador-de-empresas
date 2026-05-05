"""
Historical price chart with intrinsic-value overlays.

Layout:
- Solid line: adjusted close history (5y default).
- Dashed horizontal lines: per-model intrinsic estimates (DCF · Comps ·
  MC · RI · DDM · Aggregator), each labelled.
- Filled band between the min and max intrinsic across the surviving
  models — the "fair value range".
- Optional period pills (1Y / 3Y / 5Y / 10Y / Max) handled by the page.

Built around ``core.valuation_pipeline.ValuationResults`` so the page
just passes the bundle in.
"""
from __future__ import annotations
from typing import Iterable, Optional

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.valuation_pipeline import ValuationResults
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES, GAINS_FILL,
)


_INTRINSIC_LINE_COLORS = {
    "DCF":         TEXT_SECONDARY,
    "Comparables": TEXT_SECONDARY,
    "Monte Carlo": TEXT_SECONDARY,
    "DDM":         TEXT_SECONDARY,
    "RI":          TEXT_SECONDARY,
    "Aggregator":  ACCENT,
}


def _gather_intrinsics(results: ValuationResults) -> dict[str, float]:
    """Return ``{model_label: intrinsic}`` for every surviving model."""
    out: dict[str, float] = {}
    if results.dcf is not None:
        out["DCF"] = float(results.dcf.intrinsic_value_per_share)
    if results.comparables is not None and results.comparables.implied_per_share_median:
        out["Comparables"] = float(results.comparables.implied_per_share_median)
    if results.monte_carlo is not None:
        out["Monte Carlo"] = float(results.monte_carlo.median)
    if results.ddm is not None:
        out["DDM"] = float(results.ddm.intrinsic_value_per_share)
    if results.residual_income is not None:
        out["RI"] = float(results.residual_income.intrinsic_value_per_share)
    if (results.aggregator is not None and
            np.isfinite(results.aggregator.intrinsic_per_share)):
        out["Aggregator"] = float(results.aggregator.intrinsic_per_share)
    # Drop non-finite / non-positive values
    return {k: v for k, v in out.items()
            if v is not None and math.isfinite(v) and v > 0}


def _empty(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(text="No price history available", showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12),
                          x=0.5, y=0.5, xref="paper", yref="paper")],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def build_price_with_intrinsic_figure(
    history: pd.DataFrame,
    results: ValuationResults,
    *,
    height: int = 380,
) -> go.Figure:
    """
    Args:
        history: DataFrame with a Close column (yfinance shape).
        results: pipeline output — intrinsics + current_price for the price marker.
    """
    fig = go.Figure()
    if history is None or history.empty or "Close" not in history.columns:
        return _empty(fig, height)
    close = history["Close"].dropna()
    if close.empty:
        return _empty(fig, height)

    intrinsics = _gather_intrinsics(results)

    # ---- 1. Fair-value band (between min and max intrinsic) ----
    if len(intrinsics) >= 2:
        non_agg = {k: v for k, v in intrinsics.items() if k != "Aggregator"}
        band_pool = non_agg or intrinsics
        lo = min(band_pool.values())
        hi = max(band_pool.values())
        # Band as a filled rect: two horizontal traces at y=lo and y=hi
        fig.add_trace(go.Scatter(
            x=[close.index[0], close.index[-1]],
            y=[hi, hi],
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip", name="_band_hi",
        ))
        fig.add_trace(go.Scatter(
            x=[close.index[0], close.index[-1]],
            y=[lo, lo],
            fill="tonexty",
            fillcolor="rgba(201,169,97,0.10)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=True, name="Fair-value range",
            hovertemplate=f"Fair-value range<br>${lo:,.2f} – ${hi:,.2f}<extra></extra>",
        ))

    # ---- 2. Price line ----
    pos = float(close.iloc[-1]) >= float(close.iloc[0])
    line_color = GAINS if pos else LOSSES
    fig.add_trace(go.Scatter(
        x=close.index, y=close.values,
        mode="lines",
        line=dict(color=line_color, width=2),
        name="Price",
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>$%{y:,.2f}<extra></extra>",
    ))

    # ---- 3. Per-model horizontal dashed lines ----
    for label, value in intrinsics.items():
        is_agg = label == "Aggregator"
        color = ACCENT if is_agg else TEXT_SECONDARY
        width = 2 if is_agg else 1
        dash = "solid" if is_agg else "dash"
        fig.add_hline(
            y=value,
            line=dict(color=color, width=width, dash=dash),
            annotation=dict(
                text=f"{label}  ${value:,.2f}",
                font=dict(color=color, size=10),
                bgcolor=SURFACE, bordercolor=BORDER,
                borderpad=2, x=1.0, xanchor="right",
            ),
            annotation_position="right",
        )

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False, showline=False),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, side="right", tickprefix="$",
                   tickformat=",.0f"),
    )
    return fig
