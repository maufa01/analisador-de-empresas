"""
Owner Earnings vs Free Cash Flow — Buffett-style cash-generation view.

Owner Earnings = NI + D&A − maintenance capex − ΔWC, where maintenance
capex is approximated by rolling-N-year average D&A (Greenwald-style).
The chart overlays Owner Earnings against reported FCF to surface
gaps — persistent FCF > OE is a soft warning that capex hasn't kept
pace with depreciation.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import owner_earnings, free_cash_flow
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE, TEXT_MUTED, TEXT_SECONDARY,
)


def build_owner_earnings_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    oe = owner_earnings(income, balance, cash)
    fcf = free_cash_flow(cash)

    fig = go.Figure()

    if oe is not None:
        s = oe.dropna()
        if not s.empty:
            fig.add_trace(go.Bar(
                x=s.index, y=(s.values / 1e9),
                name="Owner Earnings",
                marker_color=ACCENT,
                text=[f"${v/1e9:.1f}B" for v in s.values],
                textposition="outside",
            ))

    if fcf is not None:
        s = fcf.dropna()
        if not s.empty:
            fig.add_trace(go.Scatter(
                x=s.index, y=(s.values / 1e9),
                name="Free Cash Flow",
                line=dict(color=GAINS, width=2, dash="dot"),
                marker=dict(size=7),
                mode="lines+markers",
            ))

    fig.update_layout(
        title=dict(text="Owner Earnings (Buffett) vs FCF",
                   font=dict(color=TEXT_SECONDARY, size=14)),
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        height=height,
        yaxis=dict(title="$B", gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig
