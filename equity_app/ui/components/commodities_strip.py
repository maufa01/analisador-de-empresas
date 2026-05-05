"""Commodities + FX strip — gold, oil, gas, DXY, Bitcoin in one line."""
from __future__ import annotations

import streamlit as st

from data.market_data import get_commodities


def _fmt_value(label: str, last: float | None) -> str:
    if last is None:
        return "—"
    if label == "Gold":      return f"${last:,.0f}"
    if label == "WTI Oil":   return f"${last:.2f}"
    if label == "NatGas":    return f"${last:.2f}"
    if label == "DXY":       return f"{last:.2f}"
    if label == "Bitcoin":   return f"${last:,.0f}"
    return f"{last:,.2f}"


def render_commodities_strip() -> None:
    data = get_commodities()
    if not any(d.get("last") is not None for d in data.values()):
        st.caption("Commodities/FX data unavailable.")
        return

    chunks: list[str] = []
    for label, d in data.items():
        value = _fmt_value(label, d.get("last"))
        chg = d.get("change_pct")
        if chg is None:
            chg_html = ""
        else:
            sign = "+" if chg >= 0 else ""
            color = "var(--gains)" if chg >= 0 else "var(--losses)"
            chg_html = (f' <span style="color:{color}; font-size:11px;">'
                        f'{sign}{chg:.2f}%</span>')
        chunks.append(
            f'<span style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.4px;">{label}</span> '
            f'<b style="color:var(--text-primary); '
            f'font-variant-numeric:tabular-nums;">{value}</b>{chg_html}'
        )

    st.markdown(
        '<div class="eq-card" style="padding:10px 16px;">'
        '<span class="eq-section-label" style="margin-right:14px;">COMMODITIES &amp; FX</span>'
        + " &nbsp; · &nbsp; ".join(chunks) +
        '</div>',
        unsafe_allow_html=True,
    )
