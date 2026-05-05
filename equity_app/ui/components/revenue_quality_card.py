"""
Revenue-quality card — score header + factor list + key volatilities.

Reads from ``analysis.revenue_quality.RevenueQuality``.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.revenue_quality import RevenueQuality


_FLAG_COLOR = {
    "green":  "var(--gains)",
    "yellow": "var(--accent)",
    "red":    "var(--losses)",
}


def _fmt_pp(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}pp"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


def _fmt_r2(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}"


def render_revenue_quality_card(res: Optional[RevenueQuality]) -> None:
    if res is None:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">REVENUE QUALITY</span>'
            '<div style="margin-top:8px;">Need at least 3 years of revenue '
            'history to compute revenue-quality factors.</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    # ---- Header ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">REVENUE QUALITY</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:34px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{res.score}/100</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{res.overall}</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'· {res.n_years} years of history</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Volatility metrics ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("σ GROSS MARGIN", _fmt_pp(res.margin_volatility_gross))
    c2.metric("σ OPERATING MARGIN", _fmt_pp(res.margin_volatility_operating))
    c3.metric("σ REV GROWTH", _fmt_pct(res.growth_volatility))
    c4.metric("R² LINEAR FIT", _fmt_r2(res.trend_r_squared))

    c5, c6, _, _ = st.columns(4, gap="small")
    c5.metric("NEG-GROWTH YEARS", str(res.negative_growth_years))
    c6.metric(
        "RECURRING PATTERN?",
        "Yes" if res.is_likely_recurring else "No",
    )

    # ---- Factor list ----
    if res.factors:
        items = "".join(
            f'<li style="display:flex; gap:10px; margin-bottom:6px; '
            f'color:var(--text-secondary); font-size:13px;">'
            f'<span style="color:{color}; min-width:14px;">{sym}</span>'
            f'<span>{msg}</span></li>'
            for sym, msg in res.factors
        )
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; margin-top:10px;">'
            '<div class="eq-section-label">FACTORS</div>'
            f'<ul style="margin:8px 0 0 0; padding:0; list-style:none;">{items}</ul>'
            '</div>',
            unsafe_allow_html=True,
        )

    if res.note:
        st.caption(res.note)
