"""
Shareholder yield card — header (total + 3y avg) + 3-metric grid +
context table.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.shareholder_yield import ShareholderYield


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
    "unknown": "var(--text-muted)",
}


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def render_shareholder_yield_card(res: ShareholderYield) -> None:
    if not res.available:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">SHAREHOLDER YIELD</span>'
            f'<div style="margin-top:8px;">{res.note}</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")
    avg_str = (f"{res.avg_3y_yield_pct:+.2f}%"
               if res.avg_3y_yield_pct is not None else "—")

    # ---- Header ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">SHAREHOLDER YIELD</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:34px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{res.total_yield_pct:+.2f}%</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{res.label}</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'· 3y avg {avg_str}</span>'
        '</div>'
        '<div style="margin-top:8px; color:var(--text-secondary); '
        f'font-size:13px; line-height:1.5;">{res.interpretation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- Breakdown ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="small")
    c1.metric("DIVIDEND YIELD", _fmt_pct(res.dividend_yield_pct))
    c2.metric("NET BUYBACK YIELD", _fmt_pct(res.net_buyback_yield_pct))
    c3.metric(
        "DILUTION DRAG",
        f"−{res.issuance_dilution_pct:.2f}%" if res.issuance_dilution_pct else "0.00%",
    )

    # ---- Context table ----
    rows_html = (
        '<tr><td style="padding:8px 12px; color:var(--text-primary);">> 8%</td>'
        '<td style="padding:8px 12px; color:var(--gains);">EXCELLENT — aggressive return</td></tr>'
        '<tr><td style="padding:8px 12px; color:var(--text-primary);">5–8%</td>'
        '<td style="padding:8px 12px; color:var(--gains);">STRONG — mature blue chips</td></tr>'
        '<tr><td style="padding:8px 12px; color:var(--text-primary);">2–5%</td>'
        '<td style="padding:8px 12px; color:var(--accent);">MODERATE — typical for growth still reinvesting</td></tr>'
        '<tr><td style="padding:8px 12px; color:var(--text-primary);">0–2%</td>'
        '<td style="padding:8px 12px; color:var(--accent);">WEAK — minimal capital return</td></tr>'
        '<tr><td style="padding:8px 12px; color:var(--text-primary);">< 0%</td>'
        '<td style="padding:8px 12px; color:var(--losses);">DILUTING — issuance exceeds returns</td></tr>'
    )
    st.markdown(
        '<div class="eq-card" style="padding:0; margin-top:10px; overflow:hidden;">'
        '<table style="width:100%; border-collapse:collapse; font-size:12px;">'
        '<thead><tr style="background:var(--surface-raised);">'
        '<th style="padding:10px 12px; text-align:left; color:var(--text-muted); '
        'font-size:11px; letter-spacing:0.6px; text-transform:uppercase;">Range</th>'
        '<th style="padding:10px 12px; text-align:left; color:var(--text-muted); '
        'font-size:11px; letter-spacing:0.6px; text-transform:uppercase;">Profile</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    if res.note:
        st.caption(res.note)
