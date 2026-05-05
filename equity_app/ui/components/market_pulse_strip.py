"""
Market-pulse strip for the Equity Analysis landing.

Compact horizontal row of 6 mini-cards: S&P 500 · Nasdaq · VIX ·
10Y Treasury yield · Gold · Bitcoin. Designed to land just above the
4-card grid so the user gets context-at-a-glance.

All HTML emitted as a single concatenated, no-leading-whitespace string
to avoid Streamlit's markdown indented-code-block trap.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from data.market_data import get_pulse_quotes


# Display label → yfinance ticker.
PULSE_SYMBOLS: dict[str, str] = {
    "S&P 500":   "^GSPC",
    "Nasdaq":    "^IXIC",
    "VIX":       "^VIX",
    "10Y Yield": "^TNX",        # quoted in % × 10 (e.g. 44.5 = 4.45%)
    "Gold":      "GC=F",        # gold futures, USD
    "Bitcoin":   "BTC-USD",
}


def _fmt_value(label: str, last: Optional[float]) -> str:
    if last is None:
        return "—"
    if label == "10Y Yield":
        # ^TNX is quoted as % × 10 → divide before suffix
        return f"{last / 10.0:.2f}%"
    if label == "VIX":
        return f"{last:.2f}"
    if label in {"S&P 500", "Nasdaq"}:
        return f"{last:,.2f}"
    if label == "Gold":
        return f"${last:,.0f}"
    if label == "Bitcoin":
        return f"${last:,.0f}"
    return f"{last:,.2f}"


def _card_html(label: str, data: dict) -> str:
    last = data.get("last")
    change_pct = data.get("change_pct")
    value_text = _fmt_value(label, last)

    if change_pct is None:
        change_html = '<span style="color:var(--text-muted);">—</span>'
    else:
        sign = "+" if change_pct >= 0 else ""
        color = "var(--gains)" if change_pct >= 0 else "var(--losses)"
        change_html = (
            f'<span style="color:{color}; font-size:11px; '
            f'font-variant-numeric:tabular-nums;">'
            f'{sign}{change_pct:.2f}%</span>'
        )

    return (
        '<div style="flex:1; min-width:120px; background:var(--surface); '
        'border:1px solid var(--border); border-radius:8px; '
        'padding:10px 12px;">'
        f'<div class="eq-idx-label" style="margin-bottom:2px;">{label}</div>'
        f'<div style="display:flex; justify-content:space-between; '
        f'align-items:baseline; gap:8px;">'
        f'<span style="color:var(--text-primary); font-size:15px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'letter-spacing:-0.3px;">{value_text}</span>'
        f'{change_html}'
        '</div></div>'
    )


def render_market_pulse_strip() -> None:
    quotes = get_pulse_quotes(tuple(PULSE_SYMBOLS.values()))
    cards_html = "".join(
        _card_html(label, quotes.get(sym, {}))
        for label, sym in PULSE_SYMBOLS.items()
    )
    st.markdown(
        '<div style="display:flex; gap:8px; flex-wrap:wrap; '
        'overflow-x:auto;">' + cards_html + '</div>',
        unsafe_allow_html=True,
    )
