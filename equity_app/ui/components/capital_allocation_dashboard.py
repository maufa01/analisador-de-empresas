"""
Capital allocation dashboard — 4 metric cards (totals + % of mkt cap)
+ a 10y stacked-bar chart + a heuristic 0-100 score with bullet flags.

Reads from ``analysis.capital_allocation.CapitalAllocationResult``.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.capital_allocation import CapitalAllocationResult
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e12: return f"${v/1e12:,.2f}T"
    if av >= 1e9:  return f"${v/1e9:,.1f}B"
    if av >= 1e6:  return f"${v/1e6:,.1f}M"
    return f"${v:,.0f}"


def _fmt_pct(v: Optional[float], *, signed: bool = False) -> str:
    if v is None:
        return "—"
    sign = "+" if (signed and v >= 0) else ""
    return f"{sign}{v * 100:.1f}%"


def _build_stacked_bar(
    annual: pd.DataFrame,
    *,
    height: int = 260,
) -> go.Figure:
    fig = go.Figure()
    if annual is None or annual.empty:
        fig.update_layout(
            height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            margin=dict(l=0, r=0, t=10, b=0),
            annotations=[dict(text="No annual capital-allocation data",
                              showarrow=False,
                              font=dict(color=TEXT_MUTED, size=12),
                              x=0.5, y=0.5, xref="paper", yref="paper")],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    x_labels = [d.strftime("%Y") if hasattr(d, "strftime") else str(d)
                for d in annual.index]
    palette = {
        "Buybacks":  "rgba(201,169,97,0.85)",
        "Dividends": "rgba(201,169,97,0.45)",
        "CapEx":     "rgba(16,185,129,0.65)",
        "M&A":       "rgba(156,163,175,0.7)",
    }

    for col in ["Buybacks", "Dividends", "CapEx", "M&A"]:
        if col not in annual.columns:
            continue
        values = (annual[col] / 1e9).values
        fig.add_trace(go.Bar(
            x=x_labels, y=values, name=col,
            marker=dict(color=palette[col]),
            hovertemplate=f"<b>%{{x}}</b><br>{col} $%{{y:,.2f}}B<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False,
                   type="category"),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, ticksuffix="B", tickprefix="$"),
        bargap=0.35,
    )
    return fig


def render_capital_allocation_dashboard(result: CapitalAllocationResult) -> None:
    """Render the full Capital Allocation tab content."""
    # ---- 4 metric cards ----
    c1, c2, c3, c4 = st.columns(4)
    cells = [
        ("BUYBACKS",     "buybacks"),
        ("DIVIDENDS",    "dividends"),
        ("CAPEX",        "capex"),
        ("M&A",          "acquisitions"),
    ]
    for col, (label, key) in zip([c1, c2, c3, c4], cells):
        total = result.totals.get(key)
        pct = result.as_pct_market_cap.get(key)
        with col:
            col.metric(
                label=label,
                value=_fmt_money(total),
                delta=(f"{pct * 100:.1f}% of mkt cap" if pct is not None else None),
            )

    # ---- Per-year stacked bar ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="eq-section-label">'
        f'CAPITAL DEPLOYED · LAST {result.years} YEARS'
        '</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        _build_stacked_bar(result.annual_cf, height=260),
        use_container_width=True, config={"displayModeBar": False},
    )

    # ---- Key metrics row ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">KEY METRICS</div>',
        unsafe_allow_html=True,
    )
    rows = [
        {"Metric": "Shareholder yield (annualised)",
         "Value": _fmt_pct(result.shareholder_yield_annualised)},
        {"Metric": "Cash conversion (FCF / Net Income)",
         "Value": _fmt_pct(result.cash_conversion)},
        {"Metric": "Incremental ROIC (window)",
         "Value": _fmt_pct(result.incremental_roic, signed=True)},
        {"Metric": "Total returned to shareholders",
         "Value": _fmt_money(result.totals.get("buybacks", 0)
                             + result.totals.get("dividends", 0))},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ---- Score + flags ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    score_color = (
        "var(--gains)" if result.score >= 70
        else "var(--accent)" if result.score >= 45
        else "var(--losses)"
    )
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px;">'
        '<div class="eq-idx-label">CAPITAL ALLOCATION SCORE</div>'
        f'<div style="font-size:32px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{score_color}; font-variant-numeric:tabular-nums; '
        f'margin-top:4px;">{result.score} / 100</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if result.flags:
        flags_html = "".join(
            f'<div style="display:flex; gap:10px; padding:6px 0; '
            f'border-bottom:1px solid var(--border); font-size:13px;">'
            f'<span style="color:var(--accent); width:14px;">{f.icon}</span>'
            f'<span style="color:var(--text-secondary);">{f.text}</span>'
            '</div>'
            for f in result.flags
        )
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; margin-top:8px;">'
            + flags_html +
            '</div>',
            unsafe_allow_html=True,
        )
