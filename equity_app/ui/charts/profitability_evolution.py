"""
ROIC / ROCE / ROA evolution — three lines, one panel.

ROCE = EBIT / (Total Assets − Current Liabilities)
ROIC and ROA come from :mod:`analysis.ratios`.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, roic, roa
from ui.theme import (
    BORDER, GAINS, LOSSES, SURFACE, TEXT_MUTED, TEXT_SECONDARY,
)


def _roce(income: pd.DataFrame, balance: pd.DataFrame):
    ebit = _get(income, "ebit")
    ta = _get(balance, "total_assets")
    cl = _get(balance, "current_liabilities")
    if ebit is None or ta is None or cl is None:
        return None
    capital_employed = ta - cl
    return ebit / capital_employed.replace(0, pd.NA)


def build_profitability_evolution(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    roic_s = roic(income, balance)
    roa_s = roa(income, balance)
    roce_s = _roce(income, balance)

    fig = go.Figure()

    def _add(series, name, color):
        if series is None:
            return
        s = series.dropna()
        if s.empty:
            return
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values * 100.0,
            mode="lines+markers+text",
            name=name,
            line=dict(color=color, width=2),
            marker=dict(size=8),
            text=[f"{v*100:.0f}%" for v in s.values],
            textposition="top center",
            textfont=dict(size=10, color=color),
        ))

    _add(roic_s, "ROIC", "#3B82F6")
    _add(roce_s, "ROCE", "#C9A961")
    _add(roa_s, "ROA", LOSSES)

    fig.update_layout(
        title=dict(text="Profitability Evolution",
                   font=dict(color=TEXT_SECONDARY, size=14)),
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        height=height,
        yaxis=dict(title="%", gridcolor=BORDER, color=TEXT_MUTED, ticksuffix="%"),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", yanchor="top", y=1.12),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig
