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
    st.Page(str(PAGES_DIR / "0_Markets.py"),             title="Markets",            default=True),
    st.Page(str(PAGES_DIR / "1_Equity_Analysis.py"),     title="Equity analysis"),
    st.Page(str(PAGES_DIR / "2_Portfolio_Optimizer.py"), title="Portfolio"),
]

# st.navigation with position="top" requires Streamlit >= 1.43.
# Older versions silently fall back to sidebar — that's fine.
try:
    nav = st.navigation(pages, position="top")
except TypeError:
    nav = st.navigation(pages)
nav.run()
