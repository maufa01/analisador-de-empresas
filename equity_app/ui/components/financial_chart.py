"""
Mini Plotly charts that sit above each financial-statement table.

- Income Statement → Revenue bars + Net Margin line (secondary y)
- Balance Sheet    → Stacked bars (Equity gold + Liabilities grey)
- Cash Flow        → FCF bars colored green/red + FCF Margin line
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, free_cash_flow
from core.formatters import format_period
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


_BASE_LAYOUT = dict(
    margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
    hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                    font=dict(color=TEXT_PRIMARY, size=12)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
)


def _empty(fig: go.Figure, height: int, msg: str) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(text=msg, showarrow=False,
                          font=dict(color=TEXT_MUTED, size=12),
                          x=0.5, y=0.5, xref="paper", yref="paper")],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


# ============================================================
# Income statement — Revenue bars + Net margin line
# ============================================================
def build_income_chart(income: pd.DataFrame, *, height: int = 220) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty:
        return _empty(fig, height, "No income statement data")
    rev = _get(income, "revenue")
    ni = _get(income, "net_income")
    if rev is None or rev.dropna().empty:
        return _empty(fig, height, "Revenue series missing")

    rev_b = rev.dropna() / 1e9
    x_labels = [format_period(d) for d in rev_b.index]

    fig.add_trace(go.Bar(
        x=x_labels, y=rev_b.values,
        name="Revenue",
        marker=dict(color="rgba(201,169,97,0.45)"),     # softer so margin line stays prominent
        hovertemplate="<b>%{x}</b><br>Revenue $%{y:,.2f}B<extra></extra>",
    ))
    if ni is not None and not ni.dropna().empty:
        ni_aligned = ni.reindex(rev_b.index)
        with pd.option_context("mode.chained_assignment", None):
            margin_pct = (ni_aligned / rev.reindex(rev_b.index) * 100.0).values
        fig.add_trace(go.Scatter(
            x=x_labels, y=margin_pct,
            mode="lines+markers", name="Net margin %",
            line=dict(color=GAINS, width=2),
            marker=dict(size=6),
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Net margin %{y:.2f}%<extra></extra>",
        ))

    fig.update_layout(
        height=height, **_BASE_LAYOUT,
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False, type="category"),
        yaxis=dict(
            title=dict(text="Revenue ($B)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
            zeroline=False, ticksuffix="B", tickprefix="$",
        ),
        yaxis2=dict(
            title=dict(text="Net margin (%)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, overlaying="y", side="right",
            showgrid=False, ticksuffix="%",
        ),
        bargap=0.35,
    )
    return fig


# ============================================================
# Balance sheet — Equity + Liabilities stacked
# ============================================================
def build_balance_chart(balance: pd.DataFrame, *, height: int = 220) -> go.Figure:
    fig = go.Figure()
    if balance is None or balance.empty:
        return _empty(fig, height, "No balance-sheet data")

    liab = _get(balance, "total_liabilities")
    eq = _get(balance, "total_equity")
    if liab is None and eq is None:
        return _empty(fig, height, "Liabilities / equity missing")

    idx = (liab.dropna().index if liab is not None
           else eq.dropna().index)
    x_labels = [format_period(d) for d in idx]
    eq_b = (eq.reindex(idx) / 1e9) if eq is not None else None
    liab_b = (liab.reindex(idx) / 1e9) if liab is not None else None

    if eq_b is not None:
        fig.add_trace(go.Bar(
            x=x_labels, y=eq_b.values, name="Equity",
            marker=dict(color=ACCENT),
            hovertemplate="<b>%{x}</b><br>Equity $%{y:,.2f}B<extra></extra>",
        ))
    if liab_b is not None:
        fig.add_trace(go.Bar(
            x=x_labels, y=liab_b.values, name="Liabilities",
            marker=dict(color=TEXT_MUTED),
            hovertemplate="<b>%{x}</b><br>Liabilities $%{y:,.2f}B<extra></extra>",
        ))

    fig.update_layout(
        height=height, **_BASE_LAYOUT,
        barmode="stack",
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False, type="category"),
        yaxis=dict(
            title=dict(text="USD ($B)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
            zeroline=False, ticksuffix="B", tickprefix="$",
        ),
        bargap=0.35,
    )
    return fig


# ============================================================
# Cash flow — FCF bars colored ± plus FCF margin line
# ============================================================
def build_fcf_chart(
    cash: pd.DataFrame,
    income: Optional[pd.DataFrame] = None,
    *,
    height: int = 220,
) -> go.Figure:
    fig = go.Figure()
    if cash is None or cash.empty:
        return _empty(fig, height, "No cash-flow data")

    fcf = free_cash_flow(cash)
    if fcf is None or fcf.dropna().empty:
        return _empty(fig, height, "FCF series missing")

    fcf_b = fcf.dropna() / 1e9
    x_labels = [format_period(d) for d in fcf_b.index]
    colors = [GAINS if v >= 0 else LOSSES for v in fcf_b.values]

    fig.add_trace(go.Bar(
        x=x_labels, y=fcf_b.values,
        marker=dict(color=colors),
        name="Free cash flow",
        hovertemplate="<b>%{x}</b><br>FCF $%{y:,.2f}B<extra></extra>",
    ))

    if income is not None and not income.empty:
        rev = _get(income, "revenue")
        if rev is not None and not rev.dropna().empty:
            rev_aligned = rev.reindex(fcf_b.index)
            margin_pct = (fcf.reindex(fcf_b.index) / rev_aligned * 100.0).values
            fig.add_trace(go.Scatter(
                x=x_labels, y=margin_pct,
                mode="lines+markers", name="FCF margin %",
                line=dict(color=ACCENT, width=2, dash="dot"),
                marker=dict(size=6),
                yaxis="y2",
                hovertemplate="<b>%{x}</b><br>FCF margin %{y:.2f}%<extra></extra>",
            ))

    fig.update_layout(
        height=height, **_BASE_LAYOUT,
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False, type="category"),
        yaxis=dict(
            title=dict(text="FCF ($B)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
            zeroline=False, ticksuffix="B", tickprefix="$",
        ),
        yaxis2=dict(
            title=dict(text="FCF margin (%)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, overlaying="y", side="right",
            showgrid=False, ticksuffix="%",
        ),
        bargap=0.35,
    )
    return fig
