"""
Hero searchbox for the Equity Analysis landing state.

A centered, large search input over the curated S&P 500 universe
(~120 tickers from ``data/ticker_universe.py``). Streamlit's
``st.selectbox`` is type-searchable out of the box — typing "Goldman"
filters to ``GS``, "Apple" → ``AAPL``, etc.

When ``data/fmp_provider`` exposes a real ``search_ticker`` endpoint the
caller can swap that in via the ``options`` argument; until then we
ship the hard-coded universe so the hero is always populated.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from data.ticker_universe import (
    SP500_TOP, labels as ticker_labels, ticker_from_label,
)


def render_landing_hero(*, key: str = "landing_searchbox") -> Optional[str]:
    """
    Render the hero header + searchbox + Analyze button.

    Returns the ticker symbol the user picked AND committed (clicked
    Analyze or pressed Enter), or ``None`` if they haven't yet.
    """
    # Top eyebrow + headline
    st.markdown(
        '<div style="text-align:center; padding-top:36px; padding-bottom:8px;">'
        '<div class="eq-section-label" style="color:var(--accent);">'
        'EQUITY RESEARCH</div>'
        '<div style="color:var(--text-primary); font-size:24px; font-weight:500; '
        'letter-spacing:-0.3px; margin-top:6px;">'
        'Analyze any public company</div>'
        '<div style="color:var(--text-muted); font-size:12px; margin-top:6px;">'
        'Type a ticker or company name and press Analyze. '
        'Press Enter to run with defaults.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Centered column with the searchbox + button
    _, mid, _ = st.columns([1, 4, 1])
    with mid:
        labels = ticker_labels(SP500_TOP)
        default_idx = next(
            (i for i, lbl in enumerate(labels) if lbl.startswith("AAPL ")),
            0,
        )
        chosen_label = st.selectbox(
            "Search ticker",
            options=labels,
            index=default_idx,
            label_visibility="collapsed",
            placeholder="🔎  Search any stock — AAPL, Microsoft, Banco …",
            key=key,
        )
        analyze = st.button(
            "Analyze",
            type="primary",
            use_container_width=True,
            key=f"{key}_analyze",
        )

    if analyze:
        return ticker_from_label(chosen_label)
    return None
