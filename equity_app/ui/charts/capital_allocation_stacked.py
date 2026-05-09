"""
Stacked bar of capital deployment — capex / buybacks / dividends /
acquisitions per year. All values rendered as positive bars (the
underlying cash-flow signs are flipped — these are outflows).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE, TEXT_MUTED, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"


def build_capital_allocation_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    capex = _get(cash, "capex")
    buybacks = _get(cash, "buybacks")
    dividends = _get(cash, "dividends_paid")

    acq = None
    if cash is not None and "acquisitionsNet" in cash.columns:
        acq = cash["acquisitionsNet"].astype(float)

    components = [
        ("CapEx",        capex,     "#3B82F6"),
        ("Buybacks",     buybacks,  ACCENT),
        ("Dividends",    dividends, GAINS),
        ("Acquisitions", acq,       _DOWNSIDE),
    ]

    fig = go.Figure()
    for label, series, color in components:
        if series is None:
            continue
        s = series.dropna()
        if s.empty:
            continue
        values = (s.abs() / 1e9)
        fig.add_trace(go.Bar(
            x=values.index, y=values.values,
            name=label, marker_color=color,
        ))

    fig.update_layout(
        title=dict(text="Capital Allocation ($B per year)",
                   font=dict(color=TEXT_SECONDARY, size=14)),
        barmode="stack",
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        height=height,
        yaxis=dict(title="$B", gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig
