"""
First-run onboarding cards explaining the three pillars of the analysis:
DCF · Comparables · Composite scoring.

Visible only when ``st.session_state["onboarding_dismissed"]`` is False.
A "Don't show again" button toggles the flag so the cards stop appearing
on subsequent loads.
"""
from __future__ import annotations

import streamlit as st


_CARDS = [
    {
        "title":  "DCF MODEL",
        "body":   ("We project free cash flows over an explicit + fade "
                   "horizon and discount them at the company's WACC. "
                   "Edit the assumptions to see how the intrinsic shifts."),
        "accent": "var(--accent)",
    },
    {
        "title":  "COMPARABLES",
        "body":   ("Apply peer-median multiples (P/E, EV/EBITDA, P/S, P/B) "
                   "to the target's fundamentals. IQR filtering removes "
                   "outlier peers automatically."),
        "accent": "var(--accent)",
    },
    {
        "title":  "COMPOSITE SCORE",
        "body":   ("A 0-100 verdict combining growth, profitability, "
                   "solvency, earnings quality and valuation upside — "
                   "delivered as Strong Buy / Buy / Hold / Sell / "
                   "Strong Sell."),
        "accent": "var(--accent)",
    },
]


def _card_html(title: str, body: str) -> str:
    return (
        '<div style="flex:1; min-width:200px; background:var(--surface); '
        'border:1px solid var(--border); border-radius:8px; '
        'padding:18px; min-height:160px;">'
        f'<div class="eq-section-label" style="color:var(--accent);">{title}</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'line-height:1.55; margin-top:8px;">{body}</div>'
        '</div>'
    )


def render_educational_cards() -> None:
    """Render the 3-card onboarding panel + a dismiss button."""
    if st.session_state.get("onboarding_dismissed"):
        return

    st.markdown(
        '<div class="eq-section-label">HOW THIS APP WORKS</div>',
        unsafe_allow_html=True,
    )
    cards_html = "".join(_card_html(c["title"], c["body"]) for c in _CARDS)
    st.markdown(
        '<div style="display:flex; gap:12px; flex-wrap:wrap;">'
        + cards_html +
        '</div>',
        unsafe_allow_html=True,
    )

    _, dismiss_col, _ = st.columns([3, 1, 3])
    with dismiss_col:
        if st.button("Don't show again",
                     key="onboarding_dismiss",
                     type="secondary",
                     use_container_width=True):
            st.session_state["onboarding_dismissed"] = True
            st.rerun()
