"""
One-line macro context strip for the Equity Analysis page header.

The full Macro dashboard page was retired (P11.A1) — for single-ticker
analysis the user only needs a quick "where are we in the cycle" sanity
check, not the full multi-tab dashboard. The strip caches at 1h since
macro series are slow-moving.

Falls back to a silent no-op when FRED_API_KEY is not configured (the
underlying ``macro_snapshot()`` returns ``available=False``).
"""
from __future__ import annotations
from typing import Optional

import streamlit as st


@st.cache_data(ttl=3600, show_spinner=False)
def _get_macro_strip_data() -> dict:
    """Pull only the 3-4 numbers the strip displays."""
    try:
        from data.fred_provider import macro_snapshot
        snap = macro_snapshot()
    except Exception:
        return {}
    if snap is None or not getattr(snap, "available", False):
        return {}

    return {
        "ten_y":     getattr(snap, "yield_10y", None),
        "fed_funds": getattr(snap, "fed_funds", None),
        "cpi_yoy":   getattr(snap, "cpi_yoy_pct", None),
        "unemp":     getattr(snap, "unemployment_rate", None),
    }


def _fmt_pct(v: Optional[float], *, suffix: str = "%") -> str:
    if v is None:
        return "—"
    return f"{v:.2f}{suffix}"


def render_macro_strip() -> None:
    """One thin row, ~40px tall, inline with the Equity Analysis header."""
    s = _get_macro_strip_data()
    if not s:
        return                               # silent no-op when FRED key missing

    cells = [
        ("10Y rate",   _fmt_pct(s.get("ten_y"))),
        ("Fed funds",  _fmt_pct(s.get("fed_funds"))),
        ("CPI YoY",    _fmt_pct(s.get("cpi_yoy"))),
        ("Unemp.",     _fmt_pct(s.get("unemp"))),
    ]
    spans = "".join(
        f'<span style="margin-right:24px;">{label}: '
        f'<b style="color:var(--text-primary); '
        f'font-variant-numeric:tabular-nums;">{value}</b></span>'
        for label, value in cells
    )
    st.markdown(
        '<div style="background:var(--surface); padding:8px 16px; '
        'border-radius:6px; font-size:11px; color:var(--text-secondary); '
        'margin-bottom:8px;">'
        + spans +
        '</div>',
        unsafe_allow_html=True,
    )
