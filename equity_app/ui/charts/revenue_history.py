"""Plotly bar chart of historical revenue (and optional FCF / Net Income overlay)."""
from __future__ import annotations
from typing import Optional, Sequence

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, free_cash_flow
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS,
)


def _empty(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(text="No revenue history", showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12),
                          x=0.5, y=0.5, xref="paper", yref="paper")],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def build_revenue_figure(
    income: pd.DataFrame,
    *,
    cash: Optional[pd.DataFrame] = None,
    height: int = 320,
    show_fcf: bool = True,
    show_net_income: bool = True,
) -> go.Figure:
    """
    Bar = Revenue. Optional overlay lines for Net Income and FCF.
    Y-axis in billions of USD.
    """
    fig = go.Figure()
    if income is None or income.empty:
        return _empty(fig, height)
    rev = _get(income, "revenue")
    if rev is None or rev.dropna().empty:
        return _empty(fig, height)

    rev_b = rev.dropna() / 1e9
    x_labels = [d.strftime("%Y") if hasattr(d, "strftime") else str(d)
                for d in rev_b.index]

    fig.add_trace(go.Bar(
        x=x_labels, y=rev_b.values,
        name="Revenue",
        # Lowered opacity so the Net Income / FCF lines stay readable on top
        marker=dict(color="rgba(201,169,97,0.45)", line=dict(color=BORDER, width=0)),
        hovertemplate="<b>%{x}</b><br>Revenue $%{y:,.2f}B<extra></extra>",
    ))

    if show_net_income:
        ni = _get(income, "net_income")
        if ni is not None and not ni.dropna().empty:
            ni_b = ni.reindex(rev_b.index) / 1e9
            fig.add_trace(go.Scatter(
                x=x_labels, y=ni_b.values,
                mode="lines+markers", name="Net income",
                line=dict(color=GAINS, width=2),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>Net income $%{y:,.2f}B<extra></extra>",
            ))

    if show_fcf and cash is not None:
        fcf = free_cash_flow(cash)
        if fcf is not None and not fcf.dropna().empty:
            fcf_b = fcf.reindex(rev_b.index) / 1e9
            fig.add_trace(go.Scatter(
                x=x_labels, y=fcf_b.values,
                mode="lines+markers", name="Free cash flow",
                line=dict(color=TEXT_SECONDARY, width=2, dash="dot"),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>FCF $%{y:,.2f}B<extra></extra>",
            ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        # type="category" forces years to be discrete so Plotly stops
        # interpolating "2020.5" between integer-like x labels.
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False, type="category"),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, ticksuffix="B", tickprefix="$"),
        bargap=0.35,
    )
    return fig
