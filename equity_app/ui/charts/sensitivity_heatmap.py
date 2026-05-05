"""
DCF sensitivity heatmap — Plotly heatmap of intrinsic per-share value
across WACC × terminal-growth (or any 2-D grid the caller passes).

Uses ``valuation.dcf_three_stage.sensitivity_table`` upstream, then
overlays:
- a ``current scenario`` marker pinning the user's WACC × g cell
- a ``current price`` reference line that the closest cell snaps to
- a diverging colour scale capped symmetrically around the current price
  so undervalued cells (intrinsic > price) read green and overvalued
  cells read red — same conventions as the rest of the app.
"""
from __future__ import annotations
from typing import Optional

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GAINS, LOSSES, ACCENT,
)


def _empty(fig: go.Figure, height: int, msg: str) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(text=msg, showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12),
                          x=0.5, y=0.5, xref="paper", yref="paper")],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def build_sensitivity_heatmap(
    sens: pd.DataFrame,
    *,
    current_price: Optional[float] = None,
    current_wacc: Optional[float] = None,
    current_g: Optional[float] = None,
    height: int = 380,
) -> go.Figure:
    """
    Args:
        sens: DataFrame indexed by WACC, columns = terminal growth.
        current_price: drawn as the colour midpoint and called out in
                       the title; None centers on the median cell.
        current_wacc / current_g: drawn as a star marker on the cell.
    """
    fig = go.Figure()
    if sens is None or sens.empty:
        return _empty(fig, height, "No sensitivity data")

    z = sens.astype(float).values
    finite = z[np.isfinite(z)]
    if finite.size == 0:
        return _empty(fig, height, "Sensitivity grid empty")

    # Symmetric colour scale around the current price (or midpoint)
    pivot = float(current_price) if (current_price and current_price > 0) else float(np.nanmedian(finite))
    spread = max(
        float(np.nanmax(np.abs(finite - pivot))),
        pivot * 0.10,
    )
    zmin = pivot - spread
    zmax = pivot + spread

    fig.add_trace(go.Heatmap(
        z=z,
        x=[f"{c:.2%}" for c in sens.columns],
        y=[f"{w:.2%}" for w in sens.index],
        zmin=zmin, zmax=zmax, zmid=pivot,
        colorscale=[
            [0.0,  LOSSES],
            [0.5,  TEXT_MUTED],
            [1.0,  GAINS],
        ],
        text=[
            [(f"${v:,.0f}" if math.isfinite(v) else "—") for v in row]
            for row in z
        ],
        texttemplate="%{text}",
        textfont=dict(family="Inter, sans-serif", size=11, color=TEXT_PRIMARY),
        hovertemplate=(
            "<b>WACC %{y}</b><br>"
            "<b>g %{x}</b><br>"
            "Intrinsic %{text}"
            f"<br>Current price ${pivot:,.2f}"
            "<extra></extra>"
        ),
        colorbar=dict(
            tickfont=dict(color=TEXT_MUTED, size=10),
            outlinewidth=0, thickness=8, len=0.85,
            tickprefix="$", tickformat=",.0f",
        ),
    ))

    # Current scenario marker (gold star at the WACC × g cell closest
    # to the user's selection)
    if current_wacc is not None and current_g is not None:
        wacc_labels = [f"{w:.2%}" for w in sens.index]
        g_labels    = [f"{c:.2%}" for c in sens.columns]
        # Snap to the nearest grid cell so the marker sits visibly even
        # when the user's exact WACC isn't on the axis.
        wi = int(np.argmin([abs(w - current_wacc) for w in sens.index]))
        ci = int(np.argmin([abs(g - current_g)    for g in sens.columns]))
        fig.add_trace(go.Scatter(
            x=[g_labels[ci]], y=[wacc_labels[wi]],
            mode="markers",
            marker=dict(symbol="star", size=14, color=ACCENT,
                        line=dict(color=TEXT_PRIMARY, width=1)),
            name="Current",
            hovertemplate=(
                "Current scenario<br>"
                f"WACC {current_wacc:.2%}<br>"
                f"g {current_g:.2%}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(
            title=dict(text="Terminal growth", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, side="top",
            showgrid=False, zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="WACC", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, autorange="reversed",
            showgrid=False, zeroline=False,
        ),
    )
    return fig
