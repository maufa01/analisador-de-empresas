"""
Watchlist panel — tabular metrics for every ticker in the watchlist.

Uses the existing :func:`analysis.parallel_loader.load_bundle` cache
(10-min TTL) instead of a separate ``cached_metrics`` column, so we
don't need a watchlist DB schema migration.

PROMPT 7 (decision journal) was never implemented, so the "Last
reviewed" column the spec proposed is omitted — wire it back in when
``data.decision_journal_db.list_decisions`` exists.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from data.watchlist_db import list_watchlist, remove_from_watchlist


def _money_compact(v) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "—"
    av = abs(v)
    if av >= 1e12:
        return f"${av/1e12:.2f}T"
    if av >= 1e9:
        return f"${av/1e9:.1f}B"
    if av >= 1e6:
        return f"${av/1e6:.1f}M"
    return f"${av:,.0f}"


def _extract_watchlist_row(ticker: str, bundle) -> dict:
    """Lean overview row — price, sector, mkt cap, last quote source.
    Full valuation lives behind a click into the Equity Analysis page."""
    info = bundle.info or {}
    quote = bundle.quote or {}
    price = quote.get("price")
    name = info.get("name") or info.get("longName") or info.get("shortName") or ticker
    return {
        "Ticker":  ticker,
        "Name":    str(name)[:24],
        "Price":   f"${price:.2f}" if price else "—",
        "Sector":  info.get("sector") or "—",
        "Mkt Cap": _money_compact(
            info.get("marketCap") or info.get("market_cap")
        ),
        "Source":  (info.get("source")
                    or (bundle.financials_source
                        if hasattr(bundle, "financials_source")
                        else "—")),
    }


def render_watchlist_panel() -> None:
    """Render the watchlist as a table with per-ticker metrics."""
    items = list_watchlist()
    if not items:
        st.info(
            "Watchlist empty. Click ☆ Add to watchlist on any ticker "
            "page to start building one."
        )
        return

    c1, c2 = st.columns([5, 1])
    with c1:
        st.caption(f"{len(items)} tickers · metrics cached for 10 minutes "
                   "(via load_bundle).")
    with c2:
        if st.button("🔄 Refresh", use_container_width=True,
                     key="watchlist_refresh"):
            st.cache_data.clear()
            st.rerun()

    # Last-reviewed timestamps from the decision journal (P7.7) —
    # show how long it's been since each ticker had a journal entry.
    try:
        from data.decision_journal_db import last_reviewed_per_ticker
        last_reviewed = last_reviewed_per_ticker()
    except Exception:
        last_reviewed = {}

    rows: list[dict] = []
    failed: list[str] = []
    progress = st.progress(0.0, text="Loading…")
    for i, ticker in enumerate(items):
        try:
            from analysis.parallel_loader import load_bundle
            bundle = load_bundle(ticker)
            if bundle.income.empty and "info" in bundle.errors:
                failed.append(ticker)
                continue
            row = _extract_watchlist_row(ticker, bundle)
            row["Last reviewed"] = (last_reviewed.get(ticker, "—") or "—")[:10]
            rows.append(row)
        except Exception:
            failed.append(ticker)
        progress.progress((i + 1) / len(items))
    progress.empty()

    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

    if failed:
        st.caption(
            f"Could not load: {', '.join(failed)} "
            "(provider chain failed — see Health page)."
        )

    # Quick-remove form (lightweight; main add/remove flow is the page header)
    with st.expander("Manage watchlist"):
        to_remove = st.selectbox("Remove ticker", [""] + items,
                                  key="wl_remove_select")
        if to_remove and st.button(f"Remove {to_remove}",
                                    key=f"wl_remove_{to_remove}"):
            remove_from_watchlist(to_remove)
            st.rerun()
