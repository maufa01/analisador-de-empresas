"""
Earnings volatility card — profile (Compounder / Stable / Cyclical /
Volatile) + four volatility metrics + factor list.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.earnings_volatility import EarningsVolatility


_FLAG_COLOR = {
    "green":  "var(--gains)",
    "yellow": "var(--accent)",
    "red":    "var(--losses)",
}


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


def _fmt_pp(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}pp"


def _fmt_r2(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}"


def render_earnings_volatility_card(res: Optional[EarningsVolatility]) -> None:
    if res is None:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">EARNINGS VOLATILITY</span>'
            '<div style="margin-top:8px;">Need at least 3 years of NI '
            'history to classify the volatility profile.</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">EARNINGS VOLATILITY · PROFILE</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:28px; font-weight:500; letter-spacing:-0.4px; '
        f'color:{color};">{res.profile}</span>'
        f'<span style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">'
        f'{res.score}/100</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'· {res.n_years} years</span>'
        '</div>'
        '<div style="margin-top:8px; color:var(--text-secondary); '
        f'font-size:13px; line-height:1.5;">{res.interpretation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("σ NI GROWTH", _fmt_pct(res.ni_growth_std_pct))
    c2.metric("σ REV GROWTH", _fmt_pct(res.revenue_growth_std_pct))
    c3.metric("σ NET MARGIN", _fmt_pp(res.net_margin_std_pp))
    c4.metric("R² NI TREND", _fmt_r2(res.ni_trend_r_squared))

    c5, c6, _, _ = st.columns(4, gap="small")
    c5.metric("LOSS YEARS", str(res.negative_ni_years))

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
