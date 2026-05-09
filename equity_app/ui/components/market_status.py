"""Market open/closed status indicator with live ET clock."""
from __future__ import annotations
from datetime import datetime, time

import streamlit as st


def _now_et() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        try:
            import pytz
            return datetime.now(pytz.timezone("America/New_York"))
        except Exception:
            return datetime.now()


def is_market_open(now: datetime | None = None) -> bool:
    """NYSE: Mon–Fri, 09:30–16:00 ET. Holidays not handled."""
    n = now or _now_et()
    if n.weekday() >= 5:
        return False
    return time(9, 30) <= n.time() < time(16, 0)


def render_status() -> None:
    """Static render of the status pill — no auto-refresh."""
    n = _now_et()
    is_open = is_market_open(n)
    label = "MARKET OPEN" if is_open else "MARKET CLOSED"
    dot_cls = "eq-status-open" if is_open else "eq-status-closed"
    clock = n.strftime("%H:%M")
    # Single-line HTML — indented f""" hits Streamlit's markdown trap.
    html = (
        f'<div class="eq-market-status" role="status" aria-live="polite">'
        f'<span class="eq-status-dot {dot_cls}" aria-hidden="true"></span>'
        f'<span>{label} · {clock} ET</span>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


@st.fragment(run_every="30s")
def render_status_live() -> None:
    """Auto-refreshing variant — re-renders only the status pill every 30s."""
    render_status()
