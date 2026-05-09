"""Index card: label / value / change with optional click-to-select button."""
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
    *,
    is_active: bool = False,
    selectable: bool = False,
    symbol: Optional[str] = None,
    on_select=None,
) -> None:
    """
    Render an index card.

    Args:
        is_active:   draws a 2px gold border around the card (used to
                     mirror the chart's currently-displayed index)
        selectable:  shows a small "Show on chart" button below the card
        symbol:      yfinance symbol passed to ``on_select`` when clicked
        on_select:   callback(symbol) — fired on the click
    """
    chg_text, chg_cls = _fmt_change(change_abs, change_pct)
    border_style = (
        "border: 2px solid var(--accent);"
        if is_active else
        "border: 1px solid var(--border);"
    )
    # Single-line HTML — indented f""" hits Streamlit's markdown
    # code-block trap (≥4 spaces ⇒ HTML rendered as literal text).
    html = (
        f'<div class="eq-card" role="group" aria-label="{label} index" '
        f'style="{border_style}">'
        f'<div class="eq-idx-label">{label}</div>'
        f'<div class="eq-idx-value">{_fmt_value(last)}</div>'
        f'<div class="eq-idx-change {chg_cls}">{chg_text}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    if selectable and symbol and on_select is not None:
        # Always use the muted outline secondary style; the gold border on
        # the card itself signals the active state. Avoids the "bright red
        # primary button" look that the previous version had.
        if st.button(
            "On chart" if is_active else "Show on chart",
            key=f"select_index_{symbol}",
            disabled=is_active,
            type="secondary",
            use_container_width=True,
        ):
            on_select(symbol)
            st.rerun()
