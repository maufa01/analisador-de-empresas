"""
Premium dark palette and global CSS for the Streamlit app.

Single source of truth — every component imports color constants from
here (never hard-codes hex values). The CSS string is injected once in
app.py and applies app-wide.

Reference look-and-feel: Koyfin, Bloomberg Terminal, Refinitiv Eikon.
The accent is a muted gold (#C9A961), NOT bright yellow.
"""
from __future__ import annotations

# ============================================================
# COLOR CONSTANTS
# ============================================================
BG_PRIMARY      = "#0B0E14"   # deep navy — main background
SURFACE         = "#131826"   # cards
SURFACE_RAISED  = "#1A2033"   # elevated surfaces (popovers, modals)
BORDER          = "#1F2937"   # subtle 1px borders
BORDER_HOVER    = "#2A3543"

TEXT_PRIMARY    = "#E8EAED"
TEXT_SECONDARY  = "#9CA3AF"
TEXT_MUTED      = "#6B7280"

ACCENT          = "#C9A961"   # muted gold
ACCENT_HOVER    = "#D4B871"
GAINS           = "#10B981"   # green
LOSSES          = "#EF4444"   # red
GAINS_FILL      = "rgba(16,185,129,0.08)"
LOSSES_FILL     = "rgba(239,68,68,0.08)"


# ============================================================
# FONT STACK
# ============================================================
FONT_STACK = (
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, 'Helvetica Neue', Arial, sans-serif"
)
FONT_MONO = "'JetBrains Mono', 'SF Mono', 'Roboto Mono', monospace"


# ============================================================
# GLOBAL CSS — injected once in app.py
# ============================================================
GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap');

:root {{
    --bg-primary: {BG_PRIMARY};
    --surface: {SURFACE};
    --surface-raised: {SURFACE_RAISED};
    --border: {BORDER};
    --border-hover: {BORDER_HOVER};
    --text-primary: {TEXT_PRIMARY};
    --text-secondary: {TEXT_SECONDARY};
    --text-muted: {TEXT_MUTED};
    --accent: {ACCENT};
    --accent-hover: {ACCENT_HOVER};
    --gains: {GAINS};
    --losses: {LOSSES};
}}

/* ---------- Base ---------- */
html, body, .stApp {{
    background-color: var(--bg-primary) !important;
    color: var(--text-primary);
    font-family: {FONT_STACK};
    font-feature-settings: "ss01", "cv01";
}}

.stApp {{ font-weight: 400; }}

* {{ font-variant-numeric: tabular-nums; }}

/* Hide default Streamlit chrome */
header[data-testid="stHeader"] {{
    background-color: transparent !important;
    height: 0 !important;
}}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
[data-testid="stDecoration"] {{ display: none; }}

/* Block container */
.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1320px !important;
}}

/* ---------- Headings ---------- */
h1, h2, h3, h4, h5 {{
    font-family: {FONT_STACK};
    font-weight: 500 !important;
    letter-spacing: -0.3px;
    color: var(--text-primary);
}}

/* Section labels (uppercase tracking) */
.eq-section-label {{
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.6px;
    color: var(--text-muted);
    margin-bottom: 8px;
}}

/* ---------- Top navigation (st.navigation position=top) ---------- */
[data-testid="stNavigation"] {{
    background-color: var(--bg-primary) !important;
    border-bottom: 1px solid var(--border);
    padding: 0 !important;
}}
[data-testid="stNavigation"] a {{
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    padding: 12px 20px !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s ease, border-color 0.15s ease;
}}
[data-testid="stNavigation"] a:hover {{
    color: var(--text-primary) !important;
}}
[data-testid="stNavigation"] a[aria-current="page"] {{
    color: var(--accent) !important;
    border-bottom-color: var(--accent) !important;
}}

/* ---------- Tabs (st.tabs) ---------- */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid var(--border);
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    padding: 12px 20px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
}}
.stTabs [aria-selected="true"] {{
    color: var(--accent) !important;
    border-bottom-color: var(--accent) !important;
}}

/* ---------- Inputs ---------- */
.stTextInput input,
.stNumberInput input {{
    background-color: var(--surface) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    font-size: 13px !important;
    padding: 8px 12px !important;
    font-family: {FONT_STACK};
}}
.stTextInput input:focus,
.stNumberInput input:focus {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
    outline: none !important;
}}
.stNumberInput button {{
    background-color: var(--surface) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
}}

/* Selectbox — BaseWeb nests several divs; we override the outer wrapper
   and let the inner value/input keep BaseWeb's vertical centering. */
.stSelectbox div[data-baseweb="select"] > div {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    min-height: 40px !important;
    font-family: {FONT_STACK};
}}
.stSelectbox div[data-baseweb="select"] [data-baseweb="select-value"],
.stSelectbox div[data-baseweb="select"] input,
.stSelectbox div[data-baseweb="select"] span {{
    color: var(--text-primary) !important;
    font-size: 13px !important;
    line-height: 1.4 !important;
}}
.stSelectbox div[data-baseweb="select"]:focus-within > div {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}}

/* Toggle (st.toggle) — match the input height so the row is visually aligned */
.stToggle > label {{
    min-height: 40px;
    display: flex !important;
    align-items: center;
}}

/* st.radio — Streamlit's default primary is a coral that clashes with the
   gold accent. Modern Streamlit renders the radio mark as an SVG; only
   that needs to be painted gold. The previous rules also coloured the
   outer container rectangle, which produced a visible 'smudge' next to
   the dot. Keep only the SVG fill. */
[data-baseweb="radio"] svg {{
    fill: var(--accent) !important;
    color: var(--accent) !important;
}}
/* Defensive: kill any background bleed on the radio's outer container
   that could re-appear with future Streamlit versions. */
[data-baseweb="radio"] [aria-checked="true"],
div[role="radiogroup"] label[data-baseweb="radio"] input[type="radio"]:checked + div,
div[role="radiogroup"] label[data-baseweb="radio"] input[type="radio"]:checked + div > div {{
    background-color: transparent !important;
    border-color: transparent !important;
    box-shadow: none !important;
}}

/* st.slider — Streamlit's default thumb + filled track ship in coral red.
   Force the brand gold so sliders match the radios + buttons. Selectors
   cover BaseWeb's nested DOM (slider thumb, filled track, range track on
   double-handle sliders) and the inner tick mark / progress fill. */
.stSlider [data-baseweb="slider"] [role="slider"],
.stSlider [data-baseweb="slider"] [role="slider"] > div,
.stSlider [data-baseweb="slider"] div[role="slider"] {{
    background-color: var(--accent) !important;
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}}
/* Filled portion of the track */
.stSlider [data-baseweb="slider"] > div:nth-child(2) > div:nth-child(1),
.stSlider [data-baseweb="slider"] > div:nth-child(2) > div:nth-child(2) {{
    background-color: var(--accent) !important;
}}
/* Inactive track */
.stSlider [data-baseweb="slider"] > div:nth-child(1),
.stSlider [data-baseweb="slider"] > div:nth-child(3) {{
    background-color: var(--border) !important;
}}
/* Streamlit also paints a min/max value bubble in coral above the thumb */
.stSlider [data-testid="stTickBarMin"],
.stSlider [data-testid="stTickBarMax"],
.stSlider [data-testid="stThumbValue"] {{
    color: var(--text-muted) !important;
}}
.stSlider [data-testid="stThumbValue"] {{
    color: var(--accent) !important;
    font-variant-numeric: tabular-nums;
}}

/* Sidebar inputs (when expanded) */
section[data-testid="stSidebar"] {{
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
}}
section[data-testid="stSidebar"] label {{
    color: var(--text-secondary) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}

/* ---------- Buttons ---------- */
.stButton > button {{
    background-color: var(--accent) !important;
    color: var(--bg-primary) !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    letter-spacing: 0.2px;
    padding: 8px 18px !important;
    transition: background-color 0.15s ease;
}}
.stButton > button:hover {{
    background-color: var(--accent-hover) !important;
    color: var(--bg-primary) !important;
}}
.stButton > button:focus {{
    box-shadow: none !important;
    outline: none !important;
}}
/* Secondary button — no fill */
.stButton > button[kind="secondary"] {{
    background-color: transparent !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: var(--border-hover) !important;
    color: var(--text-primary) !important;
}}

/* ---------- Metric ---------- */
[data-testid="stMetric"] {{
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
}}
[data-testid="stMetricLabel"] {{
    color: var(--text-muted) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}
[data-testid="stMetricValue"] {{
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    letter-spacing: -0.5px;
    font-variant-numeric: tabular-nums;
}}

/* ---------- DataFrame ---------- */
[data-testid="stDataFrame"] {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    overflow: hidden;
}}
[data-testid="stDataFrame"] * {{
    font-variant-numeric: tabular-nums;
}}

/* ---------- Radio (used for period pills) ---------- */
.eq-pills div[role="radiogroup"] {{
    gap: 6px !important;
    flex-wrap: wrap;
}}
.eq-pills label {{
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px !important;
    font-size: 12px !important;
    color: var(--text-secondary) !important;
    cursor: pointer;
    transition: all 0.15s ease;
    margin: 0 !important;
}}
.eq-pills label:hover {{
    border-color: var(--border-hover);
    color: var(--text-primary) !important;
}}
.eq-pills input:checked + div,
.eq-pills label:has(input:checked) {{
    border-color: var(--accent) !important;
    color: var(--text-primary) !important;
}}
.eq-pills div[data-testid="stRadioButton"] > div:first-child {{
    display: none;   /* hide the radio circle */
}}

/* ---------- Card primitive (HTML markup) ---------- */
.eq-card {{
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    transition: border-color 0.15s ease;
}}
.eq-card:hover {{ border-color: var(--border-hover); }}

/* ---------- Index card ---------- */
.eq-idx-label {{
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 4px;
}}
.eq-idx-value {{
    color: var(--text-primary);
    font-size: 22px;
    font-weight: 500;
    letter-spacing: -0.5px;
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
}}
.eq-idx-change {{
    font-size: 13px;
    font-weight: 500;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
}}
.eq-pos {{ color: var(--gains); }}
.eq-neg {{ color: var(--losses); }}

/* ---------- Market status ---------- */
.eq-market-status {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    justify-content: flex-end;
}}
.eq-status-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}}
.eq-status-open  {{ background-color: var(--gains);
                    box-shadow: 0 0 0 0 var(--gains);
                    animation: eq-pulse 2.4s infinite; }}
.eq-status-closed {{ background-color: var(--text-muted); }}

@keyframes eq-pulse {{
    0%   {{ box-shadow: 0 0 0 0 rgba(16,185,129,0.45); }}
    70%  {{ box-shadow: 0 0 0 6px rgba(16,185,129,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(16,185,129,0); }}
}}

/* ---------- Header metric (reusable big-number block) ---------- */
.eq-header-metric {{
    display: flex; align-items: baseline; gap: 14px;
}}
.eq-header-label {{
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}
.eq-header-value {{
    color: var(--text-primary);
    font-size: 28px;
    font-weight: 500;
    letter-spacing: -0.5px;
    font-variant-numeric: tabular-nums;
}}

/* ---------- Scrollbars ---------- */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--border-hover); }}

/* ---------- Spinner ---------- */
.stSpinner > div {{ border-top-color: var(--accent) !important; }}
</style>
"""


def inject_css() -> None:
    """Inject the global CSS block. Idempotent: safe to call once per page."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
