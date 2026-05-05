"""
Macro overlay — dedicated page for the regime call + yields curve +
vol/USD/credit metrics.

Sources are yfinance proxies only (no FRED key required). Wire FRED
later in ``analysis.macro_dashboard`` when secret-config is in place.
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


st.set_page_config(page_title="Macro · Watchlist", layout="wide")

st.markdown(
    '<div style="margin-bottom:18px;">'
    '<h1 style="color:var(--text-primary); font-size:24px; '
    'font-weight:500; letter-spacing:-0.4px; margin:0;">'
    'Macro overlay &amp; watchlist</h1>'
    '<p style="color:var(--text-muted); font-size:13px; margin-top:4px;">'
    'Treasury yield curve, vol regime, credit conditions — and the alert '
    'centre for tickers in your watchlist.'
    '</p></div>',
    unsafe_allow_html=True,
)

tab_macro, tab_alerts = st.tabs(["Macro overlay", "Watchlist alerts"])

with tab_macro:
    with st.spinner("Loading macro snapshot…"):
        snap = get_macro_snapshot()
    render_macro_panel(snap)

with tab_alerts:
    render_watchlist_alerts_panel()
