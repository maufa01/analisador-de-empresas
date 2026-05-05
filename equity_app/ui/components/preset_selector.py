"""
Preset selector — horizontal pill switch for Base / Bull / Bear / Custom.

Renders as a styled ``st.radio`` (the ``.eq-pills`` CSS class turns the
radio into pills).

Streamlit raises ``StreamlitAPIException`` if you mutate
``st.session_state[k]`` AFTER a widget with that same ``key=k`` was
already created in the current render. The "auto-flip to Custom when
the user edits a value" feature has to honour that constraint:

- We can't flip the preset *during* this render — the radio already owns
  the key.
- Instead, ``force_custom`` writes a one-shot flag and triggers a rerun.
- On the next render, ``render_preset_selector`` consumes that flag
  *before* instantiating the radio and writes the desired value into
  the session state — which is now treated as the widget's initial value
  and is therefore legal.
"""
from __future__ import annotations

import streamlit as st

from analysis.assumptions import PRESETS


def _flag_key(key: str) -> str:
    return f"__force_custom_{key}"


def render_preset_selector(
    *,
    default: str = "Base case",
    key: str = "assumptions_preset",
) -> str:
    """
    Returns the chosen preset name. Persists the selection in
    ``st.session_state[key]`` so the page can detect transitions.
    """
    # Apply any pending "force to Custom" instruction left by a previous
    # render. Mutating session_state for this key BEFORE the widget is
    # created is allowed; doing it AFTER raises StreamlitAPIException.
    flag = _flag_key(key)
    if st.session_state.pop(flag, False):
        st.session_state[key] = "Custom"

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

    Cannot mutate ``st.session_state[key]`` directly — by the time this
    runs the radio widget already owns the key. Set a one-shot flag and
    rerun; the selector consumes the flag on the next render before
    instantiating the radio.
    """
    if st.session_state.get(key) == "Custom":
        return
    flag = _flag_key(key)
    if st.session_state.get(flag):
        # A flip is already pending — avoid stacking reruns.
        return
    st.session_state[flag] = True
    st.rerun()
