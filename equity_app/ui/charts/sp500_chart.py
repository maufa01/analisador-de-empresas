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
    show_volume: bool = False,
) -> go.Figure:
    """
    Build the S&P 500 area chart.

    ``history`` is expected to have a datetime index and a ``Close`` column.
    Color is derived from the period start-vs-end direction.
    """
    if history is None or history.empty or "Close" not in history.columns:
        fig = go.Figure()
        _empty_layout(fig, height)
        return fig

    s = history["Close"].dropna()
    if s.empty:
        fig = go.Figure()
        _empty_layout(fig, height)
        return fig

    positive = float(s.iloc[-1]) >= float(s.iloc[0])
    line_color = GAINS if positive else LOSSES
    fill_color = GAINS_FILL if positive else LOSSES_FILL

    # Optional volume subplot (only when the input frame carries Volume)
    has_volume = (show_volume and "Volume" in history.columns
                  and not history["Volume"].dropna().empty)
    if has_volume:
        from plotly.subplots import make_subplots
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.72, 0.28], vertical_spacing=0.04,
        )
        price_row = 1
    else:
        fig = go.Figure()
        price_row = None

    price_trace = go.Scatter(
        x=s.index, y=s.values, mode="lines",
        line=dict(color=line_color, width=2),
        fill="tozeroy", fillcolor=fill_color,
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>%{y:,.2f}<extra></extra>",
        name="Price",
    )
    if has_volume:
        fig.add_trace(price_trace, row=1, col=1)

        vol_series = history["Volume"].dropna().reindex(s.index).fillna(0)
        # Colour each volume bar by that day's price direction
        change = s.diff()
        bar_colors = ["rgba(16,185,129,0.45)" if (c is not None and c >= 0)
                      else "rgba(239,68,68,0.45)" for c in change.values]
        fig.add_trace(
            go.Bar(
                x=vol_series.index, y=vol_series.values,
                marker=dict(color=bar_colors, line=dict(color="rgba(0,0,0,0)")),
                name="Volume",
                hovertemplate="<b>%{x|%b %d, %Y}</b><br>Vol %{y:,.0f}<extra></extra>",
                showlegend=False,
            ),
            row=2, col=1,
        )
    else:
        fig.add_trace(price_trace)

    # Tighten the price y-axis range so the fill doesn't flatten the line
    y_min, y_max = float(s.min()), float(s.max())
    pad = (y_max - y_min) * 0.10 if y_max > y_min else y_max * 0.01
    if has_volume:
        fig.update_yaxes(range=[max(y_min - pad, 0), y_max + pad], row=1, col=1)
    else:
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
    )
    fig.update_xaxes(color=TEXT_MUTED, showgrid=show_xaxis_grid,
                     gridcolor=BORDER, zeroline=False, showline=False)
    fig.update_yaxes(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                     zeroline=False, showline=False, side="right")
    if has_volume:
        # Hide y-axis labels on the volume subplot for a cleaner look
        fig.update_yaxes(showticklabels=False, row=2, col=1)

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
