"""
Landing state for the Portfolio Optimizer.

Hero header + 4 quick-start templates + a "load from watchlist" link.
Returns the chosen template (tickers + objective) when the user clicks
a card so the page can pre-populate the inputs.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st


# Each template: human-readable description + ticker tuple.
TEMPLATES: dict[str, dict] = {
    "60/40 Portfolio": {
        "blurb":     "Classic stocks / bonds split.",
        "tickers":   ("VTI", "AGG"),
        "objective": "Risk Parity",
    },
    "All-Weather": {
        "blurb":     "Ray Dalio's risk-balanced classic.",
        "tickers":   ("VTI", "TLT", "IEF", "GLD", "DBC"),
        "objective": "Risk Parity",
    },
    "Growth Tilt": {
        "blurb":     "Tech, biotech and semiconductors.",
        "tickers":   ("QQQ", "ARKK", "XLV", "SOXX"),
        "objective": "Max Sharpe",
    },
    "Low Volatility": {
        "blurb":     "Defensive minimum-volatility equity.",
        "tickers":   ("USMV", "VIG", "XLP", "XLU"),
        "objective": "Min Vol",
    },
}


def _card_html(name: str, blurb: str, tickers: tuple[str, ...]) -> str:
    ticker_chips = " · ".join(tickers)
    return (
        '<div class="eq-card" style="padding:18px; min-height:140px;">'
        f'<div class="eq-section-label" style="color:var(--accent);">{name.upper()}</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'margin-top:6px; line-height:1.4;">{blurb}</div>'
        f'<div style="color:var(--text-muted); font-size:11px; '
        f'margin-top:10px; font-variant-numeric:tabular-nums;">'
        f'{ticker_chips}</div>'
        '</div>'
    )


def render_portfolio_landing(*, watchlist_size: int = 0) -> Optional[dict]:
    """
    Render the landing. Returns the selected template's dict (with
    ``tickers`` and ``objective``) when a card is clicked, or ``None``
    if the user hasn't picked yet.

    Adds a "Load from watchlist (N)" button when ``watchlist_size > 0``;
    sets ``st.session_state["portfolio_load_watchlist"] = True`` so the
    page can branch on it.
    """
    st.markdown(
        '<div style="text-align:center; padding-top:36px; padding-bottom:8px;">'
        '<div class="eq-section-label" style="color:var(--accent);">'
        'PORTFOLIO OPTIMIZER</div>'
        '<div style="color:var(--text-primary); font-size:24px; font-weight:500; '
        'letter-spacing:-0.3px; margin-top:6px;">'
        'Build optimal portfolios using modern portfolio theory'
        '</div>'
        '<div style="color:var(--text-muted); font-size:12px; margin-top:6px;">'
        'Pick a template below or configure tickers manually.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # 2x2 grid of template cards
    keys = list(TEMPLATES.keys())
    chosen: Optional[dict] = None

    r1c1, r1c2 = st.columns(2, gap="medium")
    r2c1, r2c2 = st.columns(2, gap="medium")
    cells = [r1c1, r1c2, r2c1, r2c2]

    for cell, name in zip(cells, keys):
        with cell:
            spec = TEMPLATES[name]
            st.markdown(
                _card_html(name, spec["blurb"], spec["tickers"]),
                unsafe_allow_html=True,
            )
            if st.button(
                "Use this template",
                key=f"tmpl_{name}",
                type="secondary",
                use_container_width=True,
            ):
                chosen = {
                    "name":      name,
                    "tickers":   spec["tickers"],
                    "objective": spec["objective"],
                }

    # Watchlist loader
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    if watchlist_size > 0:
        if st.button(
            f"Load tickers from watchlist  ({watchlist_size} tickers)",
            key="load_from_watchlist",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state["portfolio_load_watchlist"] = True
            # Returning a sentinel so the page knows to read watchlist
            return {"name": "Watchlist", "tickers": tuple(), "objective": "Max Sharpe",
                    "from_watchlist": True}
    else:
        st.caption("Your watchlist is empty — add tickers from any equity analysis to load them here.")

    return chosen
