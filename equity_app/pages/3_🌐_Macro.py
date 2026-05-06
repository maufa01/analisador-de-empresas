"""
Macro · Watchlist · Superinvestors page.

Three tabs:
    - Macro overlay   — yields / vol / inflation / Sahm Rule (FRED + yfinance)
    - Watchlist alerts — events panel + per-ticker target/stop editor
    - Superinvestors  — 13F filings of famous investors (SEC EDGAR)

Macro is FRED when a key is configured, yfinance proxies otherwise.
13F is SEC EDGAR (no key needed) with a heavy-load gate per investor.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from analysis.macro_dashboard import get_macro_snapshot
from ui.components.macro_dashboard_panel import render_macro_panel
from ui.components.watchlist_alerts_panel import render_watchlist_alerts_panel
from ui.components.superinvestors_panel import render_superinvestors_panel


st.set_page_config(page_title="Macro · Watchlist · Superinvestors", layout="wide")

st.markdown(
    '<div style="margin-bottom:18px;">'
    '<h1 style="color:var(--text-primary); font-size:24px; '
    'font-weight:500; letter-spacing:-0.4px; margin:0;">'
    'Macro · Watchlist · Superinvestors</h1>'
    '<p style="color:var(--text-muted); font-size:13px; margin-top:4px;">'
    'Yield curve + inflation + recession indicators (FRED), per-ticker '
    'alert centre, and 13F filings of famous investors (SEC EDGAR).'
    '</p></div>',
    unsafe_allow_html=True,
)

tab_macro, tab_alerts, tab_supers = st.tabs([
    "Macro overlay", "Watchlist alerts", "Superinvestors",
])

with tab_macro:
    with st.spinner("Loading macro snapshot…"):
        snap = get_macro_snapshot()
    render_macro_panel(snap)

with tab_alerts:
    render_watchlist_alerts_panel()

with tab_supers:
    render_superinvestors_panel()
