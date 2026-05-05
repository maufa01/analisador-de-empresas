"""
Pre-market futures strip — only renders when the regular session is
closed. Reads ES / NQ / YM via ``data.market_data.get_premarket_futures``.
"""
from __future__ import annotations

import streamlit as st

from data.market_data import get_premarket_futures
from ui.components.market_status import is_market_open


def render_premarket_futures() -> None:
    """Render only when the regular US session is closed."""
    if is_market_open():
        return

    futures = get_premarket_futures()
    if not any(d.get("last") is not None for d in futures.values()):
        return

    chunks: list[str] = []
    for label, d in futures.items():
        last = d.get("last")
        chg = d.get("change_pct")
        last_text = f"{last:,.2f}" if last is not None else "—"
        if chg is None:
            chg_html = ""
        else:
            sign = "+" if chg >= 0 else ""
            color = "var(--gains)" if chg >= 0 else "var(--losses)"
            chg_html = (f' <span style="color:{color}; font-size:11px;">'
                        f'{sign}{chg:.2f}%</span>')
        chunks.append(
            f'<span style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.4px;">{label} fut.</span> '
            f'<b style="color:var(--text-primary); '
            f'font-variant-numeric:tabular-nums;">{last_text}</b>{chg_html}'
        )

    st.markdown(
        '<div style="text-align:right; font-size:12px; color:var(--text-secondary); '
        'padding:4px 0;">'
        '<span class="eq-section-label" style="margin-right:8px;">PRE-MKT</span>'
        + " &nbsp; · &nbsp; ".join(chunks) +
        '</div>',
        unsafe_allow_html=True,
    )
