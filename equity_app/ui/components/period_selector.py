"""Period pills (1D / 1M / 1Y / 5Y) — st.radio styled as pills."""
from __future__ import annotations
from typing import Sequence

import streamlit as st


# Mapping from UI label → yfinance period string
PERIOD_MAP: dict[str, str] = {
    "1D": "1d",
    "5D": "5d",
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
}


def render_period_selector(
    options: Sequence[str] = ("1D", "1M", "1Y", "5Y"),
    default: str = "1Y",
    key: str = "period",
) -> str:
    """Renders horizontal pills, returns the selected period label (e.g. "1Y")."""
    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    selected = st.radio(
        "period",
        options=list(options),
        index=list(options).index(default) if default in options else 0,
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return selected


def to_yf_period(label: str) -> str:
    """Translate a UI label ('1Y') to a yfinance period ('1y')."""
    return PERIOD_MAP.get(label, "1y")
