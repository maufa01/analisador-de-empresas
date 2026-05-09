"""
Render a structured per-provider error block.

Used when ``DataSourceError`` (or anything carrying ``.attempts:
list[ProviderResult]``) bubbles out of the data layer. Replaces the
generic "no-data" caption with a status table + actionable hints based
on which providers failed and why.
"""
from __future__ import annotations
from typing import Iterable, Optional

import pandas as pd
import streamlit as st

from core.provider_status import ProviderStatus


_STATUS_GLYPH: dict[ProviderStatus, str] = {
    ProviderStatus.OK:               "✓",
    ProviderStatus.MISSING_KEY:      "🔑",
    ProviderStatus.RATE_LIMITED:     "⏱",
    ProviderStatus.SCRAPE_BLOCKED:   "🚫",
    ProviderStatus.TICKER_NOT_FOUND: "❓",
    ProviderStatus.NETWORK_ERROR:    "🌐",
    ProviderStatus.NO_MATCH:         "—",
    ProviderStatus.UNKNOWN:          "?",
}


def render_provider_error_panel(
    *,
    title: str,
    message: str,
    attempts: Optional[Iterable] = None,
) -> None:
    """Show a hard error banner + (when available) a per-provider table
    plus actionable hints based on the status mix."""
    st.error(f"❌ {title}")
    if message:
        st.caption(message)

    attempts = list(attempts or [])
    if not attempts:
        return

    rows = []
    for a in attempts:
        rows.append({
            "Provider": a.provider,
            "Status":   f"{_STATUS_GLYPH.get(a.status, '?')} {a.status.value}",
            "Latency":  f"{a.latency_ms:.0f}ms" if a.latency_ms is not None else "—",
            "Detail":   a.message or "—",
        })

    with st.expander("Provider details", expanded=True):
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

        statuses = {a.status for a in attempts}
        if ProviderStatus.MISSING_KEY in statuses:
            st.info(
                "💡 At least one provider reports MISSING_KEY. Configure "
                "FMP_API_KEY (and optionally FINNHUB_API_KEY) in your "
                ".streamlit/secrets.toml or shell env."
            )
        if ProviderStatus.SCRAPE_BLOCKED in statuses:
            st.info(
                "💡 yfinance is currently scrape-blocked by Yahoo. This "
                "happens periodically — FMP should be your primary. "
                "Try `pip install --upgrade yfinance`."
            )
        if ProviderStatus.RATE_LIMITED in statuses:
            st.info(
                "💡 Hit a provider rate limit. Wait ~60 seconds and retry."
            )
        if ProviderStatus.TICKER_NOT_FOUND in statuses:
            st.info(
                "💡 Ticker may be delisted or the symbol is wrong. Try "
                "an alternate symbol (e.g. `BRK-B` instead of `BRK.B`)."
            )
