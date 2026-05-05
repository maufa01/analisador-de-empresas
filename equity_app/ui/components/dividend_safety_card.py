"""
Dividend safety card — score header + key-metrics grid + flag list +
historical dividends-paid sparkline.

Reads from ``analysis.dividend_safety.DividendSafetyResult``. When the
company does not pay dividends, renders a single muted "N/A" card so
the section never disappears silently from the layout.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.dividend_safety import DividendSafetyResult
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT,
)


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
    "unknown": "var(--text-muted)",
}


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v*100:.1f}%"


def _fmt_x(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}×"


def _fmt_years(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}y"


def _spark(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(
        y=history["dividends_paid"].values,
        mode="lines+markers",
        line=dict(color=ACCENT, width=2),
        marker=dict(size=5),
        hovertemplate="$%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=140, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_MUTED, family="Inter, sans-serif", size=10),
        xaxis=dict(visible=False),
        yaxis=dict(showgrid=True, gridcolor=BORDER, color=TEXT_MUTED,
                   tickprefix="$", tickformat=".2s"),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY)),
    )
    return fig


def render_dividend_safety_card(res: DividendSafetyResult) -> None:
    if not res.applicable:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'<span class="eq-section-label">DIVIDEND SAFETY</span>'
            f'<div style="margin-top:8px;">{res.note}</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    # ---- Header card ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">DIVIDEND SAFETY</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:34px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{res.score}/100</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{res.overall}</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Metrics grid ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("PAYOUT (NI)", _fmt_pct(res.payout_ratio_ni))
    c2.metric("FCF COVERAGE", _fmt_x(res.fcf_coverage))
    c3.metric("CASH COVERAGE", _fmt_years(res.cash_coverage_years))
    c4.metric("CONSEC. GROWTH", f"{res.consecutive_growth_years}y")

    # ---- Sparkline of dividends paid ----
    if res.history is not None and not res.history.empty and len(res.history) >= 2:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'DIVIDENDS PAID · HISTORICAL</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            _spark(res.history), use_container_width=True,
            config={"displayModeBar": False},
        )

    # ---- Flag list ----
    if res.flags:
        items = "".join(
            f'<li style="display:flex; gap:10px; margin-bottom:6px; '
            f'color:var(--text-secondary); font-size:13px;">'
            f'<span style="color:{color}; min-width:14px;">{sym}</span>'
            f'<span>{msg}</span></li>'
            for sym, msg in res.flags
        )
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; margin-top:10px;">'
            '<div class="eq-section-label">FACTORS</div>'
            f'<ul style="margin:8px 0 0 0; padding:0; list-style:none;">{items}</ul>'
            '</div>',
            unsafe_allow_html=True,
        )
