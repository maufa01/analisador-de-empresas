"""
Preset selector — horizontal pill switch for Base / Bull / Bear / Custom.

Renders as a styled ``st.radio`` (the ``.eq-pills`` CSS class turns the
radio into pills). The ``Custom`` option is the implicit landing zone
the moment the user edits any value manually — the page is responsible
for forcing the radio to that option when it detects modifications.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.assumptions import PRESETS


def render_preset_selector(
    *,
    default: str = "Base case",
    key: str = "assumptions_preset",
) -> str:
    """
    Returns the chosen preset name. Persists the selection in
    ``st.session_state[key]`` so the page can detect transitions.
    """
    if key not in st.session_state:
        st.session_state[key] = default
    current = st.session_state[key]
    if current not in PRESETS:
        current = default
        st.session_state[key] = default

    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    chosen = st.radio(
        "preset",
        options=list(PRESETS),
        index=list(PRESETS).index(current),
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    return chosen


def force_custom(key: str = "assumptions_preset") -> None:
    """
    Tell the selector that the user just edited a value manually.

    Sets the persisted preset to ``Custom`` so the next render shows it
    as active. Safe to call from anywhere in the page logic.
    """
    if st.session_state.get(key) != "Custom":
        st.session_state[key] = "Custom"
