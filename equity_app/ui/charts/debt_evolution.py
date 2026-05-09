"""
Debt evolution — D/A, D/EBITDA, and average cost of debt (Kd).

Dual-axis: ratios on the left, Kd (%) on the right.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analysis.ratios import _get
from ui.theme import (
    BORDER, LOSSES, SURFACE, TEXT_MUTED, TEXT_SECONDARY,
)


def build_debt_evolution(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    debt = _get(balance, "total_debt")
    ta = _get(balance, "total_assets")
    ebitda = _get(income, "ebitda")
    interest = _get(income, "interest_expense")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if debt is not None and ta is not None:
        da = (debt / ta.replace(0, pd.NA)).dropna()
        if not da.empty:
            fig.add_trace(go.Scatter(
                x=da.index, y=da.values,
                name="D/A",
                line=dict(color="#3B82F6", width=2),
                marker=dict(size=7),
                mode="lines+markers",
            ), secondary_y=False)

    if debt is not None and ebitda is not None:
        de = (debt / ebitda.replace(0, pd.NA)).dropna()
        if not de.empty:
            fig.add_trace(go.Scatter(
                x=de.index, y=de.values,
                name="D/EBITDA",
                line=dict(color="#C9A961", width=2),
                marker=dict(size=7),
                mode="lines+markers",
            ), secondary_y=False)

    if interest is not None and debt is not None:
        avg_debt = ((debt + debt.shift(1)) / 2).dropna()
        common = interest.dropna().index.intersection(avg_debt.index)
        if not common.empty:
            kd = (interest.loc[common].abs()
                  / avg_debt.loc[common].replace(0, pd.NA)).dropna() * 100.0
            if not kd.empty:
                fig.add_trace(go.Scatter(
                    x=kd.index, y=kd.values,
                    name="Cost of Debt (Kd)",
                    line=dict(color=LOSSES, width=2, dash="dot"),
                    marker=dict(size=7),
                    mode="lines+markers",
                ), secondary_y=True)

    fig.update_layout(
        title=dict(text="Financial Debt Evolution",
                   font=dict(color=TEXT_SECONDARY, size=14)),
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        height=height,
        legend=dict(orientation="h", y=1.12),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    fig.update_yaxes(title_text="Ratio", secondary_y=False,
                     gridcolor=BORDER, color=TEXT_MUTED)
    fig.update_yaxes(title_text="Kd %", secondary_y=True,
                     ticksuffix="%", gridcolor=BORDER, color=TEXT_MUTED)
    return fig
