"""
Sidebar API status panel.

Shows live health of every provider — pings them every 5 minutes,
or whenever the user clicks "Refresh status". Cache is keyed in
``st.session_state`` so the row of indicators is stable across reruns.

Status legend:
    ● green    OK
    ● yellow   degraded — provider responded but the response was empty
    ○ grey     not configured (missing key)
    ● copper   error
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"

_STATUS_PRESENTATION = {
    "ok":          {"color": "var(--gains)", "icon": "●", "label": "Live"},
    "degraded":    {"color": "var(--accent)", "icon": "●", "label": "Degraded"},
    "missing_key": {"color": "var(--text-muted)", "icon": "○", "label": "Not configured"},
    "error":       {"color": _DOWNSIDE, "icon": "●", "label": "Error"},
}


def _ensure_status() -> None:
    """Run health check if no cache or older than 5 min."""
    now = datetime.now(timezone.utc)
    last = st.session_state.get("_api_status_at")
    age_ok = (
        last is not None
        and isinstance(last, datetime)
        and (now - last) < timedelta(minutes=5)
    )
    if "_api_status" in st.session_state and age_ok:
        return
    from utils.health_check import run_full_health_check
    st.session_state["_api_status"] = run_full_health_check()
    st.session_state["_api_status_at"] = now


def render_api_status_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:8px;">'
            'API STATUS</div>',
            unsafe_allow_html=True,
        )

        with st.spinner("Checking providers…"):
            _ensure_status()

        status = st.session_state.get("_api_status", {}) or {}
        # Stable order so the panel doesn't jump around
        order = ("yfinance", "finnhub", "fred", "marketaux", "sec_edgar", "fmp")

        for provider in order:
            info = status.get(provider, {"status": "error", "reason": "no result"})
            s = info.get("status", "error")
            pres = _STATUS_PRESENTATION.get(s, _STATUS_PRESENTATION["error"])
            tooltip = info.get("reason", "")

            row_html = (
                '<div title="' + tooltip.replace('"', "'") + '" '
                'style="display:flex; justify-content:space-between; '
                'padding:4px 0; font-size:12px;">'
                '<span style="color:var(--text-secondary);">'
                f'<span style="color:{pres["color"]}; margin-right:6px;">'
                f'{pres["icon"]}</span>'
                f'{provider.upper()}</span>'
                f'<span style="color:{pres["color"]};">{pres["label"]}</span>'
                '</div>'
            )
            st.markdown(row_html, unsafe_allow_html=True)

        last = st.session_state.get("_api_status_at")
        if isinstance(last, datetime):
            st.caption(f"Last check: {last.astimezone().strftime('%H:%M:%S')}")

        if st.button("Refresh status", key="api_status_refresh",
                     use_container_width=True):
            from utils.health_check import run_full_health_check
            st.session_state["_api_status"] = run_full_health_check()
            st.session_state["_api_status_at"] = datetime.now(timezone.utc)
            st.rerun()
