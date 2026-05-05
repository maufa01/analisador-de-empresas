"""Plotly area chart for the S&P 500 (or any index)."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GAINS, LOSSES, GAINS_FILL, LOSSES_FILL,
)


def build_sp500_figure(
    history: pd.DataFrame,
    *,
    height: int = 320,
    show_xaxis_grid: bool = False,
) -> go.Figure:
    """
    Build the S&P 500 area chart.

    ``history`` is expected to have a datetime index and a ``Close`` column.
    Color is derived from the period start-vs-end direction.
    """
    fig = go.Figure()
    if history is None or history.empty or "Close" not in history.columns:
        _empty_layout(fig, height)
        return fig

    s = history["Close"].dropna()
    if s.empty:
        _empty_layout(fig, height)
        return fig

    positive = float(s.iloc[-1]) >= float(s.iloc[0])
    line_color = GAINS if positive else LOSSES
    fill_color = GAINS_FILL if positive else LOSSES_FILL

    fig.add_trace(
        go.Scatter(
            x=s.index,
            y=s.values,
            mode="lines",
            line=dict(color=line_color, width=2),
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>%{y:,.2f}<extra></extra>",
            name="S&P 500",
        )
    )

    # Tighten the y-axis range so the fill doesn't make the chart look flat
    y_min = float(s.min())
    y_max = float(s.max())
    pad = (y_max - y_min) * 0.10 if y_max > y_min else y_max * 0.01
    fig.update_yaxes(range=[max(y_min - pad, 0), y_max + pad])

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        showlegend=False,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=BORDER,
            font=dict(color=TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        ),
        xaxis=dict(
            color=TEXT_MUTED,
            showgrid=show_xaxis_grid,
            gridcolor=BORDER,
            zeroline=False,
            showline=False,
        ),
        yaxis=dict(
            color=TEXT_MUTED,
            showgrid=True,
            gridcolor=BORDER,
            zeroline=False,
            showline=False,
            side="right",
        ),
    )
    return fig


def _empty_layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[
            dict(
                text="No data",
                showarrow=False,
                font=dict(color=TEXT_MUTED, size=12),
                x=0.5, y=0.5, xref="paper", yref="paper",
            )
        ],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
