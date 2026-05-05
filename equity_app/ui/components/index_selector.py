"""
Grouped index selector — pills arranged by region (USA / EUROPE / ASIA / LATAM).

Renders one ``st.button`` per index using a tiny CSS trick: when the
currently-active pill matches the symbol it gets the ``[kind="primary"]``
look (gold background); the rest fall through to the muted secondary style.

Returns the selected symbol (yfinance ticker, e.g. ``"^GSPC"``).
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from data.market_data import INDEX_META


_REGION_ORDER: tuple[str, ...] = ("USA", "EUROPE", "ASIA", "LATAM")


def _by_region() -> dict[str, list[tuple[str, str]]]:
    """Returns ``{region: [(symbol, name)]}`` in canonical order."""
    out: dict[str, list[tuple[str, str]]] = {r: [] for r in _REGION_ORDER}
    for sym, meta in INDEX_META.items():
        region = meta.get("region", "USA")
        out.setdefault(region, []).append((sym, meta["name"]))
    return out


def render_index_selector(
    *,
    default: str = "^GSPC",
    key: str = "active_index_symbol",
) -> str:
    """
    Render the grouped pill selector. The currently-active pill is the
    one whose symbol equals ``st.session_state[key]``.
    """
    if key not in st.session_state:
        st.session_state[key] = default
    active: str = st.session_state[key]

    grouped = _by_region()

    for region in _REGION_ORDER:
        items = grouped.get(region, [])
        if not items:
            continue
        st.markdown(
            f'<div class="eq-section-label" '
            f'style="margin-top:6px; margin-bottom:4px;">{region}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(items))
        for col, (sym, name) in zip(cols, items):
            with col:
                is_active = (sym == active)
                clicked = st.button(
                    name, key=f"idx_pill_{sym}",
                    type=("primary" if is_active else "secondary"),
                    use_container_width=True,
                    help=f"Show {name} ({sym}) on the chart",
                )
                if clicked:
                    st.session_state[key] = sym
                    active = sym
                    st.rerun()
    return active
