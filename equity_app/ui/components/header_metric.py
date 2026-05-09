"""Big-number header metric with uppercase label."""
from __future__ import annotations
from typing import Optional

import streamlit as st


def render_header_metric(
    label: str,
    value: str,
    *,
    delta: Optional[str] = None,
    delta_positive: Optional[bool] = None,
) -> None:
    """
    Render a left-aligned big number with an uppercase label and optional
    colored delta. ``value`` and ``delta`` are pre-formatted strings — the
    caller controls precision.
    """
    delta_html = ""
    if delta:
        if delta_positive is True:
            cls = "eq-pos"
        elif delta_positive is False:
            cls = "eq-neg"
        else:
            cls = ""
        delta_html = f'<span class="eq-idx-change {cls}" style="margin-top:0;">{delta}</span>'

    # Single-line HTML to avoid Streamlit's ≥4-space-indent code-block trap.
    html = (
        f'<div>'
        f'<div class="eq-header-label">{label}</div>'
        f'<div class="eq-header-metric">'
        f'<span class="eq-header-value">{value}</span>'
        f'{delta_html}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
