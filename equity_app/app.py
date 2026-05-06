"""
Streamlit entry-point.

Sets the global page config, injects the premium dark theme CSS, and
declares top-bar navigation via st.navigation. Sidebar starts collapsed
because the WACC parameters live there but should not steal screen real
estate on every page.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is on sys.path so pages can ``from ui... import``
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from ui.theme import inject_css


# ============================================================
# Page config — runs once per session
# ============================================================
st.set_page_config(
    page_title="Equity Terminal",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()


# ============================================================
# Navigation — top bar
# ============================================================
PAGES_DIR = ROOT / "pages"

pages = [
    st.Page(str(PAGES_DIR / "0_📊_Markets.py"),             title="Markets",            default=True),
    st.Page(str(PAGES_DIR / "1_🔎_Equity_Analysis.py"),     title="Equity analysis"),
    st.Page(str(PAGES_DIR / "2_📈_Portfolio_Optimizer.py"), title="Portfolio"),
    st.Page(str(PAGES_DIR / "3_🌐_Macro.py"),               title="Macro · Watchlist"),
]

# Render the API status sidebar BEFORE nav.run() so it appears on every
# page. The component caches its check for 5 minutes via st.session_state.
try:
    from ui.components.api_status_sidebar import render_api_status_sidebar
    render_api_status_sidebar()
except Exception:
    # If the sidebar itself fails (rare — bad provider import), don't
    # block the rest of the app from rendering.
    pass

# st.navigation with position="top" requires Streamlit >= 1.43.
# Older versions silently fall back to sidebar — that's fine.
try:
    nav = st.navigation(pages, position="top")
except TypeError:
    nav = st.navigation(pages)
nav.run()
