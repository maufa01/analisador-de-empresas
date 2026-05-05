"""
Landing 2×2 grid for the Equity Analysis page:

    ┌─ YOUR WATCHLIST ──────┬─ RECENTLY ANALYZED ───┐
    │ AAPL  $185  +1.2%     │ AAPL    today          │
    │ TSLA  $340  -0.8%     │ MSFT    yesterday      │
    │ Add ticker…           │ Clear history          │
    ├─ TRENDING TODAY ──────┼─ POPULAR ANALYSIS ─────┤
    │ TSLA  +5.2%           │ S&P 500 leaders        │
    │ NVDA  +4.2%           │ Value picks            │
    │ …                     │ Growth stocks          │
    └───────────────────────┴────────────────────────┘

Each card is a function that returns the user-selected ticker (string)
or ``None``. The page wires the click → set_active_ticker(t) flow.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import streamlit as st

from data.constituents import META as TICKER_META, SP500
from data.market_data import get_movers, get_pulse_quotes
from data.popular_lists import POPULAR_LISTS
from data.watchlist_db import (
    list_watchlist, add_to_watchlist, remove_from_watchlist,
    list_recent, clear_recent,
)


# ============================================================
# Time-ago helper for "Recently analyzed"
# ============================================================
def _time_ago(iso_ts: str) -> str:
    try:
        ts = datetime.fromisoformat(iso_ts)
    except ValueError:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    secs = int(delta.total_seconds())
    if secs < 60:           return "just now"
    if secs < 3600:         return f"{secs // 60}m ago"
    if secs < 86_400:       return f"{secs // 3600}h ago"
    if secs < 86_400 * 2:   return "yesterday"
    days = secs // 86_400
    return f"{days} days ago"


# ============================================================
# WATCHLIST card
# ============================================================
def render_watchlist_card(*, on_select) -> None:
    """``on_select(ticker)`` is called when the user clicks a row."""
    tickers = list_watchlist()

    st.markdown(
        '<div class="eq-section-label">YOUR WATCHLIST</div>',
        unsafe_allow_html=True,
    )

    if not tickers:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            'Your watchlist is empty. Add tickers from any analysis using '
            'the "Add to watchlist" button.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    quotes = get_pulse_quotes(tuple(tickers))
    rows: list[str] = []
    for t in tickers:
        q = quotes.get(t, {})
        last = q.get("last")
        chg = q.get("change_pct")
        last_text = f"${last:,.2f}" if last is not None else "—"
        chg_text = (
            f'<span style="color:{("var(--gains)" if chg >= 0 else "var(--losses)")}; '
            f'font-size:12px;">{("+" if chg >= 0 else "")}{chg:.2f}%</span>'
            if chg is not None else
            '<span style="color:var(--text-muted); font-size:12px;">—</span>'
        )
        rows.append(
            '<div style="display:flex; justify-content:space-between; '
            'align-items:baseline; padding:6px 0; '
            'border-bottom:1px solid var(--border);">'
            f'<span style="color:var(--text-primary); font-weight:500; '
            f'font-size:13px;">{t}</span>'
            f'<span style="color:var(--text-muted); font-size:12px; '
            f'font-variant-numeric:tabular-nums;">{last_text}</span>'
            f'{chg_text}'
            '</div>'
        )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px;">' + "".join(rows) + '</div>',
        unsafe_allow_html=True,
    )

    # Native buttons row for click-to-select (HTML anchors don't work)
    cols = st.columns(min(len(tickers), 4))
    for i, t in enumerate(tickers[:4]):
        with cols[i]:
            if st.button(t, key=f"wl_pick_{t}",
                         type="secondary", use_container_width=True):
                on_select(t)
                st.rerun()


# ============================================================
# RECENTLY ANALYZED card
# ============================================================
def render_recently_card(*, on_select) -> None:
    rows = list_recent(limit=5)

    st.markdown(
        '<div class="eq-section-label">RECENTLY ANALYZED</div>',
        unsafe_allow_html=True,
    )
    if not rows:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            'No recent analyses yet — pick a ticker above to start.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    body = "".join(
        '<div style="display:flex; justify-content:space-between; '
        'align-items:baseline; padding:6px 0; '
        'border-bottom:1px solid var(--border);">'
        f'<span style="color:var(--text-primary); font-weight:500; '
        f'font-size:13px;">{t}</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'{_time_ago(ts)}</span>'
        '</div>'
        for t, ts in rows
    )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px;">' + body + '</div>',
        unsafe_allow_html=True,
    )

    btn_cols = st.columns(min(len(rows), 5))
    for i, (t, _) in enumerate(rows):
        with btn_cols[i]:
            if st.button(t, key=f"recent_pick_{t}",
                         type="secondary", use_container_width=True):
                on_select(t)
                st.rerun()

    if st.button("Clear history", key="recent_clear",
                 type="secondary"):
        clear_recent()
        st.rerun()


# ============================================================
# TRENDING TODAY card
# ============================================================
def render_trending_card(*, on_select) -> None:
    st.markdown(
        '<div class="eq-section-label">TRENDING TODAY</div>',
        unsafe_allow_html=True,
    )
    df = get_movers(universe=list(SP500), sort_by="gainers", top_n=5)
    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            "Couldn't fetch movers right now. Try again in a few seconds."
            '</div>',
            unsafe_allow_html=True,
        )
        return

    rows = []
    tickers: list[str] = []
    for _, r in df.iterrows():
        t = r.get("ticker")
        if not t:
            continue
        tickers.append(t)
        chg = r.get("change_pct")
        chg_text = (
            f'<span style="color:var(--gains); font-size:12px; '
            f'font-variant-numeric:tabular-nums;">'
            f'+{chg:.2f}%</span>'
            if chg is not None else
            '<span style="color:var(--text-muted); font-size:12px;">—</span>'
        )
        rows.append(
            '<div style="display:flex; justify-content:space-between; '
            'align-items:baseline; padding:6px 0; '
            'border-bottom:1px solid var(--border);">'
            f'<span style="color:var(--text-primary); font-weight:500; '
            f'font-size:13px;">{t}</span>'
            f'<span style="color:var(--text-muted); font-size:11px;">'
            f'{TICKER_META.get(t, {}).get("sector", "")}</span>'
            f'{chg_text}'
            '</div>'
        )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px;">' + "".join(rows) + '</div>',
        unsafe_allow_html=True,
    )

    btn_cols = st.columns(len(tickers) or 1)
    for i, t in enumerate(tickers):
        with btn_cols[i]:
            if st.button(t, key=f"trend_pick_{t}",
                         type="secondary", use_container_width=True):
                on_select(t)
                st.rerun()


# ============================================================
# POPULAR ANALYSIS card
# ============================================================
def render_popular_card(*, on_select) -> None:
    st.markdown(
        '<div class="eq-section-label">POPULAR ANALYSIS</div>',
        unsafe_allow_html=True,
    )
    selected = st.session_state.get("popular_list_selected")

    rows = "".join(
        '<div style="padding:6px 0; border-bottom:1px solid var(--border); '
        'color:var(--text-primary); font-size:13px;">' + name + ' '
        f'<span style="color:var(--text-muted); font-size:11px;">'
        f'· {len(tickers)} tickers</span>'
        '</div>'
        for name, tickers in POPULAR_LISTS.items()
    )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px;">' + rows + '</div>',
        unsafe_allow_html=True,
    )

    btn_cols = st.columns(len(POPULAR_LISTS))
    for i, name in enumerate(POPULAR_LISTS.keys()):
        with btn_cols[i]:
            if st.button(name.split()[0], key=f"pop_open_{name}",
                         type="secondary", use_container_width=True,
                         help=name):
                st.session_state["popular_list_selected"] = name
                st.rerun()

    if selected:
        tickers = POPULAR_LISTS.get(selected, ())
        if tickers:
            st.markdown(
                f'<div class="eq-section-label" '
                f'style="margin-top:14px; color:var(--accent);">'
                f'{selected.upper()} · {len(tickers)} TICKERS</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(min(len(tickers), 5))
            for i, t in enumerate(tickers[:5]):
                with cols[i]:
                    if st.button(t, key=f"pop_pick_{selected}_{t}",
                                 type="secondary", use_container_width=True):
                        on_select(t)
                        st.rerun()


# ============================================================
# 2×2 grid
# ============================================================
def render_landing_grid(*, on_select) -> None:
    """``on_select(ticker)`` runs whenever any card-button is clicked."""
    r1c1, r1c2 = st.columns(2, gap="medium")
    with r1c1:
        render_watchlist_card(on_select=on_select)
    with r1c2:
        render_recently_card(on_select=on_select)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    r2c1, r2c2 = st.columns(2, gap="medium")
    with r2c1:
        render_trending_card(on_select=on_select)
    with r2c2:
        render_popular_card(on_select=on_select)
