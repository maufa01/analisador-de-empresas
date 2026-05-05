"""
Histogram of Monte Carlo intrinsic-value distribution + percentile and
current-price markers.
"""
from __future__ import annotations
from typing import Optional, Sequence

import numpy as np
import plotly.graph_objects as go

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


def build_mc_distribution_figure(
    values: Sequence[float],
    *,
    percentiles: Optional[dict[int, float]] = None,
    current_price: Optional[float] = None,
    height: int = 320,
    nbins: int = 60,
) -> go.Figure:
    """
    Args:
        values:        the per-simulation intrinsic per-share values
        percentiles:   optional dict {pct: value} to overlay (e.g. {5: 53.1, 95: 498.7})
        current_price: vertical line in red dashed
    """
    fig = go.Figure()
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        _empty_layout(fig, height)
        return fig

    # Trim a fat right tail so the histogram is readable
    cap = float(np.percentile(arr, 99))
    floor = float(np.percentile(arr, 1))
    arr_view = arr[(arr >= floor) & (arr <= cap)]

    fig.add_trace(go.Histogram(
        x=arr_view,
        nbinsx=nbins,
        marker=dict(color=ACCENT, line=dict(color=BORDER, width=0.5)),
        opacity=0.85,
        hovertemplate="$%{x:,.2f}<br>%{y} sims<extra></extra>",
        name="Distribution",
        showlegend=False,
    ))

    if percentiles:
        for pct, value in percentiles.items():
            if not (floor <= value <= cap):
                continue
            fig.add_vline(
                x=float(value),
                line=dict(color=TEXT_SECONDARY, dash="dot", width=1),
                annotation=dict(
                    text=f"P{pct}",
                    font=dict(color=TEXT_MUTED, size=10),
                    bgcolor=SURFACE,
                ),
                annotation_position="top",
            )

    if current_price is not None and current_price > 0 and floor <= current_price <= cap:
        fig.add_vline(
            x=float(current_price),
            line=dict(color=LOSSES, dash="dash", width=2),
            annotation=dict(
                text=f"Price ${current_price:,.2f}",
                font=dict(color=TEXT_PRIMARY, size=11),
                bgcolor=SURFACE, bordercolor=LOSSES,
            ),
            annotation_position="top",
        )

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=24, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(
            title=dict(text="Intrinsic value per share (USD)",
                       font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER, zeroline=False,
            tickprefix="$", tickformat=",.0f",
        ),
        yaxis=dict(
            title=dict(text="Simulations", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER, zeroline=False,
        ),
        bargap=0.02,
    )
    return fig


def _empty_layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(
            text="No simulations to display", showarrow=False,
            font=dict(color=TEXT_MUTED, size=12),
            x=0.5, y=0.5, xref="paper", yref="paper",
        )],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
