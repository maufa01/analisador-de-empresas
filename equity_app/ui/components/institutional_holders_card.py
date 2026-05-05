"""
Institutional holders card — top 10 institutionals + top 5 mutual
funds + insider/institutional ownership %s.

Reads from ``analysis.institutional_analysis.HoldingsSnapshot``. Tickers
yfinance can't resolve render a clean "data unavailable" message.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import streamlit as st

from analysis.institutional_analysis import HoldingsSnapshot


def _fmt_compact(v) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    av = abs(v)
    if av >= 1e12: return f"${v / 1e12:,.2f}T"
    if av >= 1e9:  return f"${v / 1e9:,.2f}B"
    if av >= 1e6:  return f"${v / 1e6:,.1f}M"
    return f"${v:,.0f}"


def _shares_compact(v) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    av = abs(v)
    if av >= 1e9:  return f"{v / 1e9:,.2f}B"
    if av >= 1e6:  return f"{v / 1e6:,.1f}M"
    if av >= 1e3:  return f"{v / 1e3:,.1f}K"
    return f"{v:,.0f}"


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%"


def render_institutional_holders_card(snap: HoldingsSnapshot,
                                       *, target_ticker: str) -> None:
    """Render the holdings snapshot — empty state when yfinance has nothing."""
    if (snap.institutional is None or snap.institutional.empty) and \
       (snap.mutual_funds is None or snap.mutual_funds.empty):
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'No holders data returned by yfinance for <b>{target_ticker}</b>. '
            'For 13F flow tracking and historical changes, wire the FMP '
            'institutional-holdings endpoint.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ---- Ownership pct cards ----
    c1, c2 = st.columns(2)
    c1.metric("INSIDER OWNERSHIP", _pct(snap.insider_pct))
    c2.metric("INSTITUTIONAL OWNERSHIP", _pct(snap.institutional_pct))

    # ---- Top institutionals ----
    if snap.institutional is not None and not snap.institutional.empty:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:12px;">'
            'TOP INSTITUTIONAL HOLDERS</div>',
            unsafe_allow_html=True,
        )
        df = snap.institutional.copy()
        # Only project the columns that actually exist
        keep = [c for c in
                ("Holder", "shares", "value_usd", "pct_out", "date_reported")
                if c in df.columns]
        display = df[keep].head(10).reset_index(drop=True)
        if "shares" in display.columns:
            display["Shares"] = display["shares"].apply(_shares_compact)
        if "value_usd" in display.columns:
            display["Value"] = display["value_usd"].apply(_fmt_compact)
        if "pct_out" in display.columns:
            display["% Held"] = display["pct_out"].astype(float).round(2).astype(str) + "%"
        out_cols = [c for c in ("Holder", "Shares", "Value", "% Held",
                                "date_reported")
                    if c in display.columns]
        rename_dates = {"date_reported": "Reported"}
        display = display[out_cols].rename(columns=rename_dates)
        st.dataframe(display, hide_index=True, use_container_width=True)

    # ---- Top mutual funds ----
    if snap.mutual_funds is not None and not snap.mutual_funds.empty:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:12px;">'
            'TOP MUTUAL-FUND HOLDERS</div>',
            unsafe_allow_html=True,
        )
        df = snap.mutual_funds.copy()
        keep = [c for c in ("Holder", "shares", "value_usd", "pct_out")
                if c in df.columns]
        display = df[keep].head(5).reset_index(drop=True)
        if "shares" in display.columns:
            display["Shares"] = display["shares"].apply(_shares_compact)
        if "value_usd" in display.columns:
            display["Value"] = display["value_usd"].apply(_fmt_compact)
        if "pct_out" in display.columns:
            display["% Held"] = display["pct_out"].astype(float).round(2).astype(str) + "%"
        out_cols = [c for c in ("Holder", "Shares", "Value", "% Held")
                    if c in display.columns]
        st.dataframe(display[out_cols], hide_index=True, use_container_width=True)

    if snap.note:
        st.caption(snap.note)
    st.caption(
        "Snapshot from yfinance — top 10 institutionals + top 5 mutual "
        "funds. For 13F flow tracking + historical changes, wire FMP."
    )
