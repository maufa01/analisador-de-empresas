"""Revenue (bars) + Net Income & FCF (overlay lines) — buyside style.

CAGR annotation top-right, direct-label the last point of each series,
no legend.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, free_cash_flow
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEUTRAL, COLOR_PRIMARY,
    COLOR_TEXT_MUTED, _annotate_last, _base_layout, _cagr,
    _empty_layout, _fy_labels,
)


def build_revenue_figure(
    income: pd.DataFrame,
    *,
    cash: Optional[pd.DataFrame] = None,
    height: int = CHART_HEIGHT,
    show_fcf: bool = True,
    show_net_income: bool = True,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty:
        fig.update_layout(**_empty_layout("No revenue history", height=height))
        return fig
    rev = _get(income, "revenue")
    if rev is None or rev.dropna().empty:
        fig.update_layout(**_empty_layout("No revenue history", height=height))
        return fig

    rev_b = rev.dropna() / 1e9
    x = _fy_labels(rev_b.index)

    fig.add_trace(go.Bar(
        x=x, y=rev_b.values,
        name="Revenue",
        marker=dict(color="rgba(201,161,74,0.55)"),
        hovertemplate="<b>%{x}</b><br>Revenue $%{y:,.2f}B<extra></extra>",
        showlegend=False,
    ))
    _annotate_last(fig, x, rev_b.values, label="Revenue", color=COLOR_PRIMARY)

    if show_net_income:
        ni = _get(income, "net_income")
        if ni is not None and not ni.dropna().empty:
            ni_b = ni.reindex(rev_b.index) / 1e9
            fig.add_trace(go.Scatter(
                x=x, y=ni_b.values,
                mode="lines+markers", name="Net income",
                line=dict(color=COLOR_GROWTH, width=2),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>Net income $%{y:,.2f}B<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, ni_b.dropna().values,
                           label="Net income", color=COLOR_GROWTH)

    if show_fcf and cash is not None:
        fcf = free_cash_flow(cash)
        if fcf is not None and not fcf.dropna().empty:
            fcf_b = fcf.reindex(rev_b.index) / 1e9
            fig.add_trace(go.Scatter(
                x=x, y=fcf_b.values,
                mode="lines+markers", name="FCF",
                line=dict(color=COLOR_GROWTH, width=2, dash="dot"),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>FCF $%{y:,.2f}B<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, fcf_b.dropna().values,
                           label="FCF", color=COLOR_GROWTH)

    layout = _base_layout(
        height=height,
        y_tickprefix="$", y_ticksuffix="B",
    )
    layout["bargap"] = 0.35
    fig.update_layout(**layout)

    # Revenue CAGR annotation (top-right) — span the visible window
    n = len(rev_b)
    if n >= 2:
        g = _cagr(float(rev_b.iloc[0]), float(rev_b.iloc[-1]), n - 1)
        if g is not None:
            fig.add_annotation(
                xref="paper", yref="paper",
                x=1.0, y=1.06,
                xanchor="right", yanchor="bottom",
                showarrow=False,
                text=f"<b>Revenue CAGR · {n - 1}y: {g*100:+.1f}%</b>",
                font=dict(size=10, color=COLOR_PRIMARY),
            )
    return fig
