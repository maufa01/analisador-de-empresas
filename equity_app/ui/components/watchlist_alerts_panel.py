"""
Watchlist + alerts admin panel.

Renders three sections:
    - Unacknowledged alert events
    - Per-ticker meta editor (target / stop / notes / tags)
    - "Run alert checks now" button

Reads/writes via ``data.watchlist_alerts_db`` and ``data.watchlist_db``.
"""
from __future__ import annotations

import streamlit as st

from data.watchlist_alerts_db import (
    list_events, acknowledge_event, acknowledge_all_events,
    upsert_meta, get_meta,
)
from data.watchlist_db import list_watchlist
from analysis.alert_checker import check_all


def render_watchlist_alerts_panel() -> None:
    # ---- Unacknowledged events ----
    events = list_events(only_unack=True, limit=20)

    head_cols = st.columns([4, 1])
    with head_cols[0]:
        st.markdown(
            '<div class="eq-section-label">WATCHLIST ALERTS · '
            f'{len(events)} UNREAD</div>',
            unsafe_allow_html=True,
        )
    with head_cols[1]:
        if st.button("Run checks now", use_container_width=True, type="primary"):
            with st.spinner("Checking watchlist…"):
                triggered = check_all()
            st.success(f"{len(triggered)} alerts triggered.")
            st.rerun()

    if not events.empty:
        for _, row in events.iterrows():
            cols = st.columns([5, 1])
            with cols[0]:
                st.markdown(
                    '<div class="eq-card" style="padding:12px 16px;">'
                    f'<span style="color:var(--accent); font-weight:500;">'
                    f'{row["ticker"]}</span>'
                    f'<span style="color:var(--text-muted); margin:0 8px;">·</span>'
                    f'<span style="color:var(--text-secondary); font-size:13px;">'
                    f'{row["message"]}</span>'
                    f'<div style="color:var(--text-muted); font-size:11px; '
                    f'margin-top:4px;">{row["kind"]} · {row["triggered_at"]}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if st.button("Mark read", key=f"ack_{row['id']}",
                             use_container_width=True):
                    acknowledge_event(int(row["id"]))
                    st.rerun()

        if st.button("Mark all read"):
            acknowledge_all_events()
            st.rerun()
    else:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            'No unread alerts. Add target/stop prices below to start tracking.'
            '</div>',
            unsafe_allow_html=True,
        )

    # ---- Per-ticker meta ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'TARGETS · STOPS · NOTES</div>',
        unsafe_allow_html=True,
    )

    tickers = list_watchlist()
    if not tickers:
        st.caption("Add tickers to your watchlist from the Markets page first.")
        return

    selected = st.selectbox("Edit ticker", tickers, key="wl_meta_select")
    meta = get_meta(selected)
    cols = st.columns(3, gap="small")
    with cols[0]:
        target_price = st.number_input(
            "Target price", min_value=0.0,
            value=float(meta.get("target_price") or 0.0),
            step=1.0, key=f"wl_target_{selected}",
        )
    with cols[1]:
        stop_loss = st.number_input(
            "Stop loss", min_value=0.0,
            value=float(meta.get("stop_loss") or 0.0),
            step=1.0, key=f"wl_stop_{selected}",
        )
    with cols[2]:
        st.write("")
        st.write("")
        if st.button("Save", use_container_width=True, key=f"wl_save_{selected}"):
            upsert_meta(
                selected,
                target_price=(target_price if target_price > 0 else None),
                stop_loss=(stop_loss if stop_loss > 0 else None),
            )
            st.success(f"Saved {selected}")
            st.rerun()

    notes = st.text_area(
        "Notes", value=meta.get("notes", ""),
        key=f"wl_notes_{selected}", height=80,
    )
    if st.button("Save notes", key=f"wl_notes_save_{selected}"):
        upsert_meta(selected, notes=notes)
        st.success("Notes saved")
        st.rerun()

    if meta.get("last_score") is not None:
        st.caption(
            f"Last check: score {meta.get('last_score')} · "
            f"rating {meta.get('last_rating') or '—'} · "
            f"checked {meta.get('last_checked_at') or '—'}"
        )
