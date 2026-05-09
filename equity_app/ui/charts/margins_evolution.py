"""Margin evolution — Gross / Operating / Net (drop EBITDA, less noisy)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import calculate_ratios
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEUTRAL, COLOR_PRIMARY,
    _annotate_last, _base_layout, _empty_layout, _fy_labels,
)


# Three colors only — the spec asks to drop EBITDA margin to keep the
# chart legible at 5y horizon.
_MARGIN_TRACES = [
    ("Gross Margin %",     "Gross",     COLOR_PRIMARY),
    ("Operating Margin %", "Operating", COLOR_GROWTH),
    ("Net Margin %",       "Net",       COLOR_NEUTRAL),
]


def build_margins_figure(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty:
        fig.update_layout(**_empty_layout("No margin history", height=height))
        return fig
    try:
        ratios = calculate_ratios(income, balance, cash)
    except Exception:
        fig.update_layout(**_empty_layout("No margin history", height=height))
        return fig
    if ratios is None or ratios.empty:
        fig.update_layout(**_empty_layout("No margin history", height=height))
        return fig

    x_full = _fy_labels(ratios.index)
    plotted = 0
    for col, short, color in _MARGIN_TRACES:
        if col not in ratios.columns:
            continue
        s = ratios[col].dropna()
        if s.empty:
            continue
        x = _fy_labels(s.index)
        fig.add_trace(go.Scatter(
            x=x, y=s.values,
            mode="lines+markers", name=short,
            line=dict(color=color, width=2),
            marker=dict(size=6),
            hovertemplate=f"<b>%{{x}}</b><br>{short} margin %{{y:.1f}}%<extra></extra>",
            showlegend=False,
        ))
        _annotate_last(fig, x, s.values,
                       label=f"{short} {s.iloc[-1]:.1f}%", color=color)
        plotted += 1

    if plotted == 0:
        fig.update_layout(**_empty_layout("No margin history", height=height))
        return fig

    fig.update_layout(**_base_layout(height=height, y_ticksuffix="%"))
    return fig
