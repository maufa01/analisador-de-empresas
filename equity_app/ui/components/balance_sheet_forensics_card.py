"""
Balance-sheet forensics card — score header + key-ratios grid + flag
list. Reads from ``analysis.balance_sheet_quality.BalanceSheetQuality``.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.balance_sheet_quality import BalanceSheetQuality


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
}


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v*100:.1f}%"


def _fmt_billions(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12: return f"{sign}${av / 1e12:,.2f}T"
    if av >= 1e9:  return f"{sign}${av / 1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av / 1e6:,.1f}M"
    return f"{sign}${av:,.0f}"


def _fmt_x(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}×"


def render_balance_sheet_forensics(res: Optional[BalanceSheetQuality]) -> None:
    if res is None:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">BALANCE-SHEET FORENSICS</span>'
            '<div style="margin-top:8px;">Balance sheet not available — '
            'forensics cannot be computed.</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    # ---- Header ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">BALANCE-SHEET FORENSICS</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:34px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{res.score}/100</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{res.overall}</span>'
        '</div>'
        '<div style="margin-top:8px; color:var(--text-secondary); '
        f'font-size:13px; line-height:1.5;">{res.interpretation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- Metrics grid ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("GOODWILL % ASSETS", _fmt_pct(res.goodwill_pct))
    c2.metric("OTHER INTANGIBLES %", _fmt_pct(res.intangibles_pct))
    c3.metric("TANGIBLE BV", _fmt_billions(res.tangible_book_value))
    c4.metric("DEBT / ASSETS", _fmt_pct(res.debt_to_assets))

    c5, c6, _, _ = st.columns(4, gap="small")
    c5.metric("CASH / DEBT", _fmt_x(res.cash_to_debt))
    if res.receivables_revenue_diff_pp is not None:
        delta_str = f"{res.receivables_revenue_diff_pp:+.0f}pp YoY"
    else:
        delta_str = "—"
    c6.metric("RECEIVABLES vs REVENUE", delta_str)

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
            '<div class="eq-section-label">FORENSIC SIGNALS</div>'
            f'<ul style="margin:8px 0 0 0; padding:0; list-style:none;">{items}</ul>'
            '</div>',
            unsafe_allow_html=True,
        )

    if res.goodwill_trend != "stable":
        trend_msg = {
            "aggressive_ma": "Goodwill more than doubled in 5y — aggressive M&A.",
            "writedowns":    "Goodwill cut sharply in 5y — past acquisitions impaired.",
        }.get(res.goodwill_trend, "")
        if trend_msg:
            st.caption(trend_msg)
