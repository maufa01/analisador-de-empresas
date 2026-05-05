"""Plotly line chart of gross / operating / net / EBITDA margins over time."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import calculate_ratios
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


_MARGIN_COLORS = {
    "Gross Margin %":      ACCENT,
    "EBITDA Margin %":     GAINS,
    "Operating Margin %":  TEXT_SECONDARY,
    "Net Margin %":        LOSSES,
}


def _empty(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(text="No margin history available",
                          showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12),
                          x=0.5, y=0.5, xref="paper", yref="paper")],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def build_margins_figure(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 320,
) -> go.Figure:
    """Plot any of the four margins that ``calculate_ratios`` produces."""
    fig = go.Figure()
    if income is None or income.empty:
        return _empty(fig, height)
    try:
        ratios = calculate_ratios(income, balance, cash)
    except Exception:
        return _empty(fig, height)
    if ratios is None or ratios.empty:
        return _empty(fig, height)

    x_labels = [d.strftime("%Y") if hasattr(d, "strftime") else str(d)
                for d in ratios.index]
    plotted = 0
    for name, color in _MARGIN_COLORS.items():
        if name not in ratios.columns:
            continue
        series = ratios[name].dropna()
        if series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=x_labels[-len(series):], y=series.values,
            mode="lines+markers", name=name.replace(" %", ""),
            line=dict(color=color, width=2),
            marker=dict(size=6),
            hovertemplate=f"<b>%{{x}}</b><br>{name} %{{y:.2f}}%<extra></extra>",
        ))
        plotted += 1

    if plotted == 0:
        return _empty(fig, height)

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
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, ticksuffix="%"),
    )
    return fig
