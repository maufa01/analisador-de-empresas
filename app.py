"""
Streamlit Cloud entry point.

Delegates to the v2 application that lives in ``equity_app/``. Streamlit
Cloud (and ``streamlit run app.py``) load this file by default — keeping
this thin shim at the repo root means the deploy and the directory-based
project layout can coexist.
"""
from __future__ import annotations
import sys
from pathlib import Path

# ``equity_app`` is added to sys.path so its modules (ui, data, analysis,
# valuation, portfolio, scoring) resolve as top-level imports — same way
# they do when running ``streamlit run equity_app/app.py`` 
# 
# 
# directly.
ROOT = Path(__file__).resolve().parent / "equity_app"
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
    st.Page(str(PAGES_DIR / "0_📊_Markets.py"),         title="Markets",          default=True),
    st.Page(str(PAGES_DIR / "1_🔎_Equity_Analysis.py"), title="Equity analysis"),
    st.Page(str(PAGES_DIR / "2_📈_Portfolio.py"),       title="Portfolio"),
    st.Page(str(PAGES_DIR / "3_⚖_Compare.py"),          title="Compare"),
    st.Page(str(PAGES_DIR / "4_📓_Journal.py"),         title="Journal"),
    st.Page(str(PAGES_DIR / "9_🔧_Health.py"),          title="Health"),
]

# st.navigation with position="top" requires Streamlit >= 1.43.
# Older versions silently fall back to sidebar.
try:
    nav = st.navigation(pages, position="top")
except TypeError:
    nav = st.navigation(pages)
nav.run()











