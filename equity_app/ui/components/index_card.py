"""Index card: label / value / change. Renders compact HTML."""
from __future__ import annotations
from typing import Optional

import streamlit as st


def _fmt_value(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


def _fmt_change(abs_chg: Optional[float], pct_chg: Optional[float]) -> tuple[str, str]:
    if abs_chg is None or pct_chg is None:
        return "—", ""
    sign = "+" if pct_chg >= 0 else ""
    cls = "eq-pos" if pct_chg >= 0 else "eq-neg"
    return f"{sign}{pct_chg:.2f}% · {sign}{abs_chg:,.2f}", cls


def render_index_card(
    label: str,
    last: Optional[float],
    change_abs: Optional[float],
    change_pct: Optional[float],
) -> None:
    chg_text, chg_cls = _fmt_change(change_abs, change_pct)
    html = f"""
    <div class="eq-card" role="group" aria-label="{label} index">
        <div class="eq-idx-label">{label}</div>
        <div class="eq-idx-value">{_fmt_value(last)}</div>
        <div class="eq-idx-change {chg_cls}">{chg_text}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
