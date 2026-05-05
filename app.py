"""
Equity Terminal — Streamlit dashboard with Bloomberg-style UI.

Run:
    streamlit run app.py
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from fetcher import fetch_data, fetch_peers, fetch_price_panel
from ratios import calculate_ratios
from dcf import (
    dcf_model,
    build_dcf_inputs_from_company,
    calculate_wacc,
    sensitivity_table,
)
from comparables import comparables_model
from scoring import scoring_model
from markowitz import (
    expected_returns,
    covariance_matrix,
    optimize_max_sharpe,
    optimize_min_vol,
    efficient_frontier,
)
from config import DEFAULT_WACC_PARAMS, DCF_DEFAULTS, PORTFOLIO_DEFAULTS

# ============================================================
# THEME
# ============================================================
COL_BG = "#0B0F14"
COL_CARD = "#121821"
COL_BORDER = "#1E2733"
COL_BORDER_HOVER = "#2A3543"
COL_TEXT = "#E6E8EB"
COL_TEXT_DIM = "#9AA4AF"
COL_AMBER = "#F5C542"
COL_GREEN = "#3FB950"
COL_RED = "#F85149"

st.set_page_config(
    page_title="EQUITY TERMINAL",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CSS
# ============================================================
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Roboto+Mono:wght@400;500;600&display=swap');

html, body, .stApp, [class*="css"] {{
    background-color: {COL_BG} !important;
    color: {COL_TEXT};
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 13px;
    text-align: left;
}}

.block-container {{
    padding: 0.6rem 1.2rem 1rem 1.2rem !important;
    max-width: 100% !important;
}}

#MainMenu, footer, header[data-testid="stHeader"] {{
    visibility: hidden;
    height: 0;
}}

h1, h2, h3, h4, h5, h6 {{
    color: {COL_TEXT};
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    letter-spacing: 0.3px;
}}

p, span, div, label {{
    color: {COL_TEXT};
}}

/* === SIDEBAR === */
section[data-testid="stSidebar"] {{
    background-color: {COL_CARD} !important;
    border-right: 1px solid {COL_BORDER};
    padding-top: 0.4rem;
}}
section[data-testid="stSidebar"] > div {{
    padding-top: 0.5rem;
}}
section[data-testid="stSidebar"] label {{
    color: {COL_TEXT_DIM} !important;
    font-size: 10px !important;
    font-weight: 500 !important;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}}
section[data-testid="stSidebar"] input {{
    background-color: {COL_BG} !important;
    color: {COL_TEXT} !important;
    border: 1px solid {COL_BORDER} !important;
    border-radius: 2px !important;
    font-family: 'Roboto Mono', monospace !important;
    font-size: 12px !important;
    padding: 4px 8px !important;
    text-align: right;
}}
section[data-testid="stSidebar"] input:focus {{
    border-color: {COL_AMBER} !important;
    box-shadow: none !important;
}}
section[data-testid="stSidebar"] [data-testid="stNumberInput"] button {{
    background-color: {COL_BG} !important;
    border: 1px solid {COL_BORDER} !important;
    color: {COL_TEXT_DIM} !important;
}}
section[data-testid="stSidebar"] [data-testid="stNumberInput"] {{
    margin-bottom: 0.2rem !important;
}}
section[data-testid="stSidebar"] [data-testid="stNumberInput"] > div {{
    margin-bottom: 0 !important;
}}

/* === MAIN INPUTS === */
.stTextInput input, .stNumberInput input {{
    background-color: {COL_CARD} !important;
    color: {COL_TEXT} !important;
    border: 1px solid {COL_BORDER} !important;
    border-radius: 2px !important;
    font-family: 'Roboto Mono', monospace !important;
    font-size: 12px !important;
    padding: 6px 10px !important;
}}
.stTextInput input:focus {{
    border-color: {COL_AMBER} !important;
    box-shadow: none !important;
}}

/* === BUTTONS === */
.stButton > button {{
    background-color: {COL_AMBER} !important;
    color: {COL_BG} !important;
    border: none !important;
    border-radius: 2px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase;
    padding: 8px 22px !important;
    transition: background-color 0.15s ease;
    width: 100%;
}}
.stButton > button:hover {{
    background-color: #FFD75A !important;
    color: {COL_BG} !important;
}}
.stButton > button:focus {{
    box-shadow: none !important;
    outline: none !important;
}}

/* === TABS === */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    background-color: {COL_CARD};
    border-bottom: 1px solid {COL_BORDER};
    margin-bottom: 0.8rem;
}}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent !important;
    color: {COL_TEXT_DIM} !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    padding: 12px 22px !important;
    border: none !important;
    border-radius: 0 !important;
}}
.stTabs [aria-selected="true"] {{
    color: {COL_AMBER} !important;
    border-bottom: 2px solid {COL_AMBER} !important;
    background-color: transparent !important;
}}

/* === TOP BAR === */
.term-topbar {{
    display: flex;
    align-items: stretch;
    background-color: {COL_CARD};
    border: 1px solid {COL_BORDER};
    border-radius: 2px;
    padding: 0;
    margin-bottom: 12px;
    overflow: hidden;
}}
.term-topbar-cell {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 10px 18px;
    border-right: 1px solid {COL_BORDER};
}}
.term-topbar-cell:last-child {{ border-right: none; }}
.term-topbar-label {{
    color: {COL_TEXT_DIM};
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    margin-bottom: 4px;
}}
.term-topbar-value {{
    color: {COL_TEXT};
    font-family: 'Roboto Mono', monospace;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.2;
}}
.term-topbar-ticker {{
    color: {COL_AMBER};
    font-family: 'Roboto Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 1.5px;
    line-height: 1.2;
}}

/* === SECTION HEADER === */
.term-section {{
    color: {COL_AMBER};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    border-bottom: 1px solid {COL_BORDER};
    padding-bottom: 6px;
    margin-top: 20px;
    margin-bottom: 10px;
}}

.term-sidebar-header {{
    color: {COL_AMBER};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.6px;
    text-transform: uppercase;
    border-bottom: 1px solid {COL_BORDER};
    padding-bottom: 4px;
    margin-top: 14px;
    margin-bottom: 8px;
}}

.term-sidebar-readonly {{
    color: {COL_TEXT_DIM};
    font-family: 'Roboto Mono', monospace;
    font-size: 11px;
    padding: 2px 0;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px dotted {COL_BORDER};
}}

/* === VALUATION CARDS === */
.term-card {{
    background-color: {COL_CARD};
    border: 1px solid {COL_BORDER};
    border-left: 2px solid {COL_BORDER};
    border-radius: 2px;
    padding: 12px 18px;
    height: 100%;
    transition: border-color 0.15s ease;
}}
.term-card:hover {{ border-color: {COL_BORDER_HOVER}; }}
.term-card-label {{
    color: {COL_TEXT_DIM};
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 6px;
}}
.term-card-value {{
    font-family: 'Roboto Mono', monospace;
    font-size: 24px;
    font-weight: 700;
    line-height: 1.1;
    color: {COL_TEXT};
}}
.term-card-sub {{
    color: {COL_TEXT_DIM};
    font-family: 'Roboto Mono', monospace;
    font-size: 10px;
    margin-top: 4px;
    letter-spacing: 0.3px;
}}

/* === DATA PANELS === */
.term-panel {{
    background-color: {COL_CARD};
    border: 1px solid {COL_BORDER};
    border-radius: 2px;
    padding: 0;
}}

.term-kv-table {{
    width: 100%;
    border-collapse: collapse;
}}
.term-kv-table td {{
    font-family: 'Roboto Mono', monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-bottom: 1px solid {COL_BORDER};
}}
.term-kv-table td:first-child {{
    color: {COL_TEXT_DIM};
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.6px;
    width: 50%;
}}
.term-kv-table td:last-child {{
    color: {COL_TEXT};
    text-align: right;
    font-weight: 500;
}}
.term-kv-table tr:last-child td {{ border-bottom: none; }}

/* === DATAFRAMES === */
[data-testid="stDataFrame"] {{
    background-color: {COL_CARD} !important;
    border: 1px solid {COL_BORDER} !important;
    border-radius: 2px !important;
}}
[data-testid="stDataFrame"] > div {{
    background-color: {COL_CARD} !important;
}}

/* === EXPANDER === */
[data-testid="stExpander"] {{
    background-color: {COL_CARD} !important;
    border: 1px solid {COL_BORDER} !important;
    border-radius: 2px !important;
}}
[data-testid="stExpander"] summary {{
    color: {COL_TEXT_DIM} !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 8px 14px !important;
}}
[data-testid="stExpander"] summary:hover {{ color: {COL_AMBER} !important; }}

/* === EMPTY STATE === */
.term-empty {{
    background-color: {COL_CARD};
    border: 1px dashed {COL_BORDER};
    border-radius: 2px;
    color: {COL_TEXT_DIM};
    font-family: 'Roboto Mono', monospace;
    font-size: 11px;
    text-align: center;
    padding: 60px 20px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* === ALERTS === */
[data-testid="stAlert"] {{
    background-color: {COL_CARD} !important;
    border: 1px solid {COL_BORDER} !important;
    border-left: 3px solid {COL_AMBER} !important;
    border-radius: 2px !important;
    color: {COL_TEXT} !important;
    font-family: 'Roboto Mono', monospace;
    font-size: 11px !important;
}}

/* === CHECKBOX === */
.stCheckbox label {{
    color: {COL_TEXT_DIM} !important;
    font-size: 11px !important;
    font-family: 'Inter', sans-serif !important;
}}

/* === SCROLLBAR === */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: {COL_BG}; }}
::-webkit-scrollbar-thumb {{ background: {COL_BORDER}; border-radius: 0; }}
::-webkit-scrollbar-thumb:hover {{ background: {COL_BORDER_HOVER}; }}

/* === SPINNER === */
.stSpinner > div {{ border-top-color: {COL_AMBER} !important; }}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ============================================================
# HELPERS — formatters
# ============================================================
def fmt_money(val, prec: int = 2) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"${val:,.{prec}f}"


def fmt_pct(val, prec: int = 2, signed: bool = False) -> str:
    if val is None or pd.isna(val):
        return "—"
    sign = "+" if signed and val >= 0 else ""
    return f"{sign}{val:.{prec}f}%"


def fmt_mcap(val) -> str:
    if val is None or pd.isna(val):
        return "—"
    if val >= 1e12:
        return f"${val/1e12:.2f}T"
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    if val >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


# ============================================================
# HELPERS — UI components
# ============================================================
def render_topbar(
    ticker, name, price, change_pct, market_cap, sector
) -> None:
    chg_color = COL_TEXT_DIM
    chg_str = "—"
    if change_pct is not None and pd.notna(change_pct):
        chg_color = COL_GREEN if change_pct >= 0 else COL_RED
        sign = "+" if change_pct >= 0 else ""
        chg_str = f"{sign}{change_pct:.2f}%"

    name_disp = (name or "—")[:42]

    html = f"""
    <div class="term-topbar">
        <div class="term-topbar-cell" style="min-width: 110px;">
            <div class="term-topbar-label">Ticker</div>
            <div class="term-topbar-ticker">{ticker or "—"}</div>
        </div>
        <div class="term-topbar-cell" style="flex: 2; min-width: 240px;">
            <div class="term-topbar-label">Company</div>
            <div class="term-topbar-value" style="font-size: 13px;">{name_disp}</div>
        </div>
        <div class="term-topbar-cell" style="min-width: 120px;">
            <div class="term-topbar-label">Last Price</div>
            <div class="term-topbar-value">{fmt_money(price)}</div>
        </div>
        <div class="term-topbar-cell" style="min-width: 110px;">
            <div class="term-topbar-label">Change</div>
            <div class="term-topbar-value" style="color: {chg_color};">{chg_str}</div>
        </div>
        <div class="term-topbar-cell" style="min-width: 130px;">
            <div class="term-topbar-label">Market Cap</div>
            <div class="term-topbar-value">{fmt_mcap(market_cap)}</div>
        </div>
        <div class="term-topbar-cell" style="flex: 1.2; min-width: 160px;">
            <div class="term-topbar-label">Sector</div>
            <div class="term-topbar-value" style="font-size: 12px;">{sector or "—"}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_card(label: str, value: str, accent: str = COL_TEXT, sub: str | None = None) -> None:
    sub_html = f'<div class="term-card-sub">{sub}</div>' if sub else ""
    html = f"""
    <div class="term-card" style="border-left-color: {accent};">
        <div class="term-card-label">{label}</div>
        <div class="term-card-value" style="color: {accent};">{value}</div>
        {sub_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_section(text: str) -> None:
    st.markdown(f'<div class="term-section">▎ {text}</div>', unsafe_allow_html=True)


def render_sidebar_header(text: str) -> None:
    st.markdown(f'<div class="term-sidebar-header">{text}</div>', unsafe_allow_html=True)


def render_kv_table(rows: list[tuple[str, str]]) -> None:
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    st.markdown(
        f'<div class="term-panel"><table class="term-kv-table">{body}</table></div>',
        unsafe_allow_html=True,
    )


def style_table(df: pd.DataFrame, fmt: str = "{:.2f}", highlight_row: str | None = None):
    """Bloomberg-style dense table styling."""
    styled = df.style.format(fmt, na_rep="—")
    styled = styled.set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("background-color", COL_BG),
                    ("color", COL_TEXT_DIM),
                    ("font-family", "Inter, sans-serif"),
                    ("font-weight", "500"),
                    ("font-size", "10px"),
                    ("text-transform", "uppercase"),
                    ("letter-spacing", "1px"),
                    ("text-align", "right"),
                    ("border-bottom", f"1px solid {COL_BORDER}"),
                    ("padding", "6px 10px"),
                ],
            },
            {
                "selector": "th.row_heading",
                "props": [
                    ("text-align", "left"),
                    ("color", COL_TEXT_DIM),
                ],
            },
            {
                "selector": "td",
                "props": [
                    ("font-family", "Roboto Mono, monospace"),
                    ("font-size", "11px"),
                    ("color", COL_TEXT),
                    ("text-align", "right"),
                    ("background-color", COL_CARD),
                    ("border-bottom", f"1px solid {COL_BORDER}"),
                    ("padding", "5px 10px"),
                ],
            },
        ]
    )
    if highlight_row is not None:
        def _hl(row):
            if row.name == highlight_row:
                return [
                    f"background-color: rgba(245, 197, 66, 0.10); "
                    f"color: {COL_AMBER}; font-weight: 600;"
                ] * len(row)
            return [""] * len(row)
        styled = styled.apply(_hl, axis=1)
    return styled


def plotly_theme(fig: go.Figure, title: str | None = None, height: int = 240) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=COL_CARD,
        plot_bgcolor=COL_CARD,
        font=dict(family="Inter, sans-serif", color=COL_TEXT, size=10),
        margin=dict(l=44, r=14, t=36 if title else 14, b=28),
        height=height,
        showlegend=False,
        title=dict(
            text=title,
            font=dict(family="Inter", size=10, color=COL_AMBER),
            x=0.01,
            xanchor="left",
        ) if title else None,
    )
    fig.update_xaxes(
        gridcolor=COL_BORDER,
        linecolor=COL_BORDER,
        zerolinecolor=COL_BORDER,
        tickfont=dict(size=9, color=COL_TEXT_DIM),
        showgrid=False,
    )
    fig.update_yaxes(
        gridcolor=COL_BORDER,
        linecolor=COL_BORDER,
        zerolinecolor=COL_BORDER,
        tickfont=dict(size=9, color=COL_TEXT_DIM),
        gridwidth=1,
    )
    return fig


def years_index(df: pd.DataFrame) -> list:
    return [d.year if hasattr(d, "year") else str(d) for d in df.index]


# ============================================================
# TABS
# ============================================================
tabs = st.tabs(["▎ EQUITY ANALYSIS", "▎ PORTFOLIO OPTIMIZER"])

# ============================================================
# TAB 1 — STOCK ANALYSIS
# ============================================================
with tabs[0]:
    # ---------- Sidebar: DCF parameters ----------
    with st.sidebar:
        render_sidebar_header("WACC COMPONENTS")
        beta = st.number_input("BETA", value=1.20, step=0.10, format="%.2f")
        rf = st.number_input(
            "RISK-FREE RATE",
            value=DEFAULT_WACC_PARAMS["risk_free_rate"],
            step=0.005, format="%.3f",
        )
        erp = st.number_input(
            "EQUITY RISK PREMIUM",
            value=DEFAULT_WACC_PARAMS["market_risk_premium"],
            step=0.005, format="%.3f",
        )
        kd = st.number_input(
            "COST OF DEBT",
            value=DEFAULT_WACC_PARAMS["cost_of_debt"],
            step=0.005, format="%.3f",
        )
        tax = st.number_input(
            "TAX RATE",
            value=DEFAULT_WACC_PARAMS["tax_rate"],
            step=0.05, format="%.2f",
        )

        render_sidebar_header("CAPITAL STRUCTURE")
        we_pct = st.number_input(
            "EQUITY %",
            value=DEFAULT_WACC_PARAMS["weight_equity"] * 100,
            min_value=0.0, max_value=100.0, step=5.0, format="%.1f",
        )
        we = we_pct / 100.0
        wd = 1.0 - we
        st.markdown(
            f'<div class="term-sidebar-readonly">'
            f'<span>DEBT %</span><span>{wd*100:.1f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        render_sidebar_header("PROJECTION")
        proj_years = st.number_input(
            "YEARS",
            value=DCF_DEFAULTS["projection_years"],
            min_value=3, max_value=10, step=1,
        )
        tg = st.number_input(
            "TERMINAL GROWTH",
            value=DCF_DEFAULTS["terminal_growth"],
            step=0.005, format="%.3f",
        )
        manual_g = st.number_input(
            "OVERRIDE GROWTH (0=CAGR)",
            value=0.0, step=0.01, format="%.2f",
        )

    # ---------- Command bar ----------
    cb1, cb2, cb3 = st.columns([1.2, 3, 1])
    with cb1:
        ticker = st.text_input(
            "Ticker", value="AAPL",
            label_visibility="collapsed",
            placeholder="TICKER",
        ).strip().upper()
    with cb2:
        peers_input = st.text_input(
            "Peers", value="MSFT,GOOGL,META",
            label_visibility="collapsed",
            placeholder="PEERS (COMMA SEPARATED)",
        )
    with cb3:
        analyze = st.button("ANALYZE", type="primary", key="btn_analyze")

    # ---------- Run analysis ----------
    if analyze:
        with st.spinner(f"Loading {ticker} & peers..."):
            try:
                target = fetch_data(ticker)
                peer_tk = [t.strip() for t in peers_input.split(",") if t.strip()]
                peers_data = fetch_peers(peer_tk)
                peers_list = list(peers_data.values())
            except Exception as e:
                st.error(f"Fetch error: {e}")
                st.stop()

        ratios_df = calculate_ratios(
            target.income_stmt, target.balance_sheet, target.cash_flow
        )

        wacc = calculate_wacc(beta, rf, erp, kd, tax, we, wd)
        dcf_res = None
        dcf_inputs_obj = None
        intrinsic_dcf = None
        try:
            dcf_inputs_obj = build_dcf_inputs_from_company(
                target, wacc=wacc, terminal_growth=tg,
                projection_years=proj_years,
                growth_rate=manual_g if manual_g != 0 else None,
            )
            dcf_res = dcf_model(dcf_inputs_obj)
            intrinsic_dcf = dcf_res.intrinsic_per_share
        except Exception as e:
            st.warning(f"DCF unavailable: {e}")

        comps = None
        intrinsic_comps = None
        try:
            comps = comparables_model(target, peers_list)
            intrinsic_comps = comps["average_implied"]
        except Exception as e:
            st.warning(f"Comparables unavailable: {e}")

        candidates = [
            v for v in [intrinsic_dcf, intrinsic_comps]
            if v is not None and pd.notna(v)
        ]
        intrinsic_avg = sum(candidates) / len(candidates) if candidates else None
        price = target.current_price
        score = scoring_model(ratios_df, price, intrinsic_avg) if intrinsic_avg else None

        change_pct = None
        if not target.prices.empty and len(target.prices) >= 2:
            try:
                change_pct = float(
                    (target.prices["Close"].iloc[-1] / target.prices["Close"].iloc[-2] - 1) * 100
                )
            except Exception:
                change_pct = None

        st.session_state.analysis = {
            "target": target,
            "ratios_df": ratios_df,
            "wacc": wacc,
            "dcf_res": dcf_res,
            "dcf_inputs": dcf_inputs_obj,
            "intrinsic_dcf": intrinsic_dcf,
            "comps": comps,
            "intrinsic_comps": intrinsic_comps,
            "intrinsic_avg": intrinsic_avg,
            "price": price,
            "change_pct": change_pct,
            "score": score,
            "tg": tg,
        }

    # ---------- Render ----------
    data = st.session_state.get("analysis")

    if not data:
        render_topbar(None, None, None, None, None, None)
        st.markdown(
            '<div class="term-empty">Enter a ticker and click ANALYZE to load data</div>',
            unsafe_allow_html=True,
        )
    else:
        target = data["target"]
        info = target.info or {}
        name = info.get("longName") or info.get("shortName") or target.ticker
        sector = info.get("sector")

        render_topbar(
            ticker=target.ticker,
            name=name,
            price=data["price"],
            change_pct=data["change_pct"],
            market_cap=target.market_cap,
            sector=sector,
        )

        # ===== VALUATION SUMMARY =====
        render_section("VALUATION SUMMARY")
        ic = data["intrinsic_avg"]
        cp = data["price"]
        sc = data["score"]
        upside_pct = sc["upside"] * 100 if sc else None
        rating = sc["rating"] if sc else "—"

        if upside_pct is None:
            up_color = COL_TEXT_DIM
        elif upside_pct >= 10:
            up_color = COL_GREEN
        elif upside_pct < -10:
            up_color = COL_RED
        else:
            up_color = COL_AMBER

        rating_color = {
            "STRONG BUY": COL_GREEN,
            "BUY": COL_GREEN,
            "HOLD": COL_AMBER,
            "SELL": COL_RED,
        }.get(rating, COL_TEXT_DIM)

        v1, v2, v3, v4 = st.columns(4)
        with v1:
            render_card(
                "Intrinsic Value", fmt_money(ic), COL_AMBER,
                sub=f"DCF {fmt_money(data['intrinsic_dcf'])} · Comps {fmt_money(data['intrinsic_comps'])}",
            )
        with v2:
            render_card("Current Price", fmt_money(cp), COL_TEXT)
        with v3:
            render_card(
                "Upside",
                fmt_pct(upside_pct, prec=1, signed=True),
                up_color,
                sub=f"Score {sc['score']:.0f}/100" if sc else None,
            )
        with v4:
            render_card("Recommendation", rating, rating_color)

        # ===== DCF + COMPS DETAIL =====
        render_section("DCF & COMPARABLES DETAIL")
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; '
                f'letter-spacing:1px; text-transform:uppercase; margin-bottom:6px;">'
                f'Discounted Cash Flow</div>',
                unsafe_allow_html=True,
            )
            if data["dcf_res"]:
                dcf_res = data["dcf_res"]
                render_kv_table([
                    ("WACC", fmt_pct(data['wacc'] * 100, prec=2)),
                    ("Growth used", fmt_pct(dcf_res.growth_used * 100, prec=2)),
                    ("Terminal growth", fmt_pct(data['tg'] * 100, prec=2)),
                    ("Enterprise Value", f"${dcf_res.enterprise_value/1e9:,.2f}B"),
                    ("Equity Value", f"${dcf_res.equity_value/1e9:,.2f}B"),
                    ("Intrinsic / share", fmt_money(data['intrinsic_dcf'])),
                ])
            else:
                st.markdown(
                    '<div class="term-empty" style="padding:20px;">DCF not available</div>',
                    unsafe_allow_html=True,
                )

        with d2:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; '
                f'letter-spacing:1px; text-transform:uppercase; margin-bottom:6px;">'
                f'Comparables — Implied Prices</div>',
                unsafe_allow_html=True,
            )
            if data["comps"] and not data["comps"]["implied_prices"].empty:
                rows = [
                    (str(k), fmt_money(float(v)))
                    for k, v in data["comps"]["implied_prices"].items()
                ]
                rows.append(("Average", fmt_money(data["intrinsic_comps"])))
                render_kv_table(rows)
            else:
                st.markdown(
                    '<div class="term-empty" style="padding:20px;">Comparables not available</div>',
                    unsafe_allow_html=True,
                )

        # ===== HISTORICAL CHARTS =====
        render_section("HISTORICAL")
        ratios_df = data["ratios_df"]
        x_years = years_index(ratios_df)

        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            if "Revenue" in ratios_df.columns:
                fig = go.Figure(go.Bar(
                    x=x_years,
                    y=(ratios_df["Revenue"] / 1e9).values,
                    marker=dict(color=COL_AMBER, line=dict(width=0)),
                    width=0.55,
                ))
                fig = plotly_theme(fig, "REVENUE ($B)")
                st.plotly_chart(fig, use_container_width=True)
        with ch2:
            if "FCF" in ratios_df.columns:
                fcf_vals = (ratios_df["FCF"] / 1e9).values
                colors = [COL_GREEN if v >= 0 else COL_RED for v in fcf_vals]
                fig = go.Figure(go.Bar(
                    x=x_years,
                    y=fcf_vals,
                    marker=dict(color=colors, line=dict(width=0)),
                    width=0.55,
                ))
                fig = plotly_theme(fig, "FREE CASH FLOW ($B)")
                st.plotly_chart(fig, use_container_width=True)
        with ch3:
            if "EBITDA Margin %" in ratios_df.columns:
                fig = go.Figure(go.Scatter(
                    x=x_years,
                    y=ratios_df["EBITDA Margin %"].values,
                    mode="lines+markers",
                    line=dict(color=COL_AMBER, width=1.5),
                    marker=dict(size=5, color=COL_AMBER),
                ))
                fig = plotly_theme(fig, "EBITDA MARGIN %")
                st.plotly_chart(fig, use_container_width=True)

        # Price vs intrinsic chart
        if not target.prices.empty and data["intrinsic_avg"]:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=target.prices.index,
                y=target.prices["Close"],
                mode="lines",
                line=dict(color=COL_AMBER, width=1.2),
                name="Price",
            ))
            fig.add_hline(
                y=data["intrinsic_avg"],
                line=dict(color=COL_GREEN, width=1, dash="dash"),
                annotation=dict(
                    text=f"Intrinsic {fmt_money(data['intrinsic_avg'])}",
                    font=dict(color=COL_GREEN, size=10),
                    bgcolor=COL_CARD,
                ),
            )
            fig = plotly_theme(fig, "PRICE vs INTRINSIC VALUE", height=260)
            st.plotly_chart(fig, use_container_width=True)

        # ===== RATIOS TABLE =====
        render_section("FINANCIAL RATIOS")
        ratio_only_cols = [
            c for c in ratios_df.columns
            if c not in ("Revenue", "EBITDA", "Net Income", "FCF")
        ]
        if ratio_only_cols:
            rdf = ratios_df[ratio_only_cols].copy()
            rdf.index = [d.strftime("%Y") if hasattr(d, "strftime") else str(d) for d in rdf.index]
            st.dataframe(
                style_table(rdf.T, fmt="{:.2f}"),
                use_container_width=True,
            )

        # ===== COMPARABLES TABLE =====
        if data["comps"] is not None:
            render_section("COMPARABLES")
            comps = data["comps"]
            tm = comps["target_multiples"]
            peers_table = comps["peers_table"]

            def _safe_div(a, b):
                if a is None or b is None or b == 0 or pd.isna(a) or pd.isna(b):
                    return np.nan
                return a / b * 100

            rows = [{
                "Company": tm["ticker"],
                "P/E": tm["P/E"],
                "EV/EBITDA": tm["EV/EBITDA"],
                "EV/Sales": tm["EV/Sales"],
                "P/B": tm["P/B"],
                "ROE %": _safe_div(tm["NetIncome"], tm["Equity"]),
                "Margin %": _safe_div(tm["NetIncome"], tm["Revenue"]),
            }]
            for tk, prow in peers_table.iterrows():
                rows.append({
                    "Company": tk,
                    "P/E": prow.get("P/E"),
                    "EV/EBITDA": prow.get("EV/EBITDA"),
                    "EV/Sales": prow.get("EV/Sales"),
                    "P/B": prow.get("P/B"),
                    "ROE %": _safe_div(prow.get("NetIncome"), prow.get("Equity")),
                    "Margin %": _safe_div(prow.get("NetIncome"), prow.get("Revenue")),
                })
            comp_df = pd.DataFrame(rows).set_index("Company")
            st.dataframe(
                style_table(comp_df, fmt="{:.2f}", highlight_row=tm["ticker"]),
                use_container_width=True,
            )

        # ===== SENSITIVITY (collapsible) =====
        if data["dcf_res"] and data["dcf_inputs"] is not None:
            with st.expander("SENSITIVITY  ·  WACC × TERMINAL GROWTH"):
                try:
                    sens = sensitivity_table(data["dcf_inputs"])
                    st.dataframe(
                        sens.style.format("${:.2f}").background_gradient(
                            cmap="RdYlGn", axis=None
                        ),
                        use_container_width=True,
                    )
                except Exception as e:
                    st.warning(f"Sensitivity not computable: {e}")

        # ===== SCORE BREAKDOWN =====
        if data["score"]:
            with st.expander("SCORE BREAKDOWN"):
                comp = data["score"]["components"]
                bb1, bb2, bb3, bb4 = st.columns(4)
                with bb1: render_card("Growth", f"{comp['growth']:.0f}", COL_AMBER)
                with bb2: render_card("Profitability", f"{comp['profitability']:.0f}", COL_AMBER)
                with bb3: render_card("Solvency", f"{comp['solvency']:.0f}", COL_AMBER)
                with bb4: render_card("Valuation", f"{comp['valuation']:.0f}", COL_AMBER)

# ============================================================
# TAB 2 — PORTFOLIO
# ============================================================
with tabs[1]:
    render_section("MARKOWITZ PORTFOLIO OPTIMIZER")

    pc1, pc2, pc3, pc4 = st.columns([3.5, 1, 1, 1])
    with pc1:
        pf_input = st.text_input(
            "Tickers", value="AAPL,MSFT,GOOGL,JNJ,XOM,JPM,KO",
            label_visibility="collapsed",
            placeholder="PORTFOLIO TICKERS",
        )
    with pc2:
        rf_pf = st.number_input(
            "RF rate",
            value=PORTFOLIO_DEFAULTS["risk_free_rate"],
            step=0.005, format="%.3f", key="rf_pf",
            label_visibility="collapsed",
        )
    with pc3:
        years_pf = st.number_input(
            "Years",
            value=5, min_value=1, max_value=10, step=1,
            label_visibility="collapsed",
        )
    with pc4:
        opt_btn = st.button("OPTIMIZE", type="primary", key="btn_opt")

    allow_short = st.checkbox("Allow short selling", value=False)

    if opt_btn:
        tickers = [t.strip().upper() for t in pf_input.split(",") if t.strip()]
        if len(tickers) < 2:
            st.error("Minimum 2 tickers required.")
            st.stop()

        with st.spinner("Loading prices..."):
            prices = fetch_price_panel(tickers, years=years_pf).dropna()

        if prices.empty:
            st.error("No prices retrieved.")
            st.stop()

        mu = expected_returns(prices)
        cov = covariance_matrix(prices)

        try:
            sharpe_p = optimize_max_sharpe(mu, cov, risk_free=rf_pf, allow_short=allow_short)
            minvol_p = optimize_min_vol(mu, cov, allow_short=allow_short)
        except Exception as e:
            st.error(f"Optimization failed: {e}")
            st.stop()

        # Portfolio summary cards
        render_section("OPTIMAL PORTFOLIOS")
        op1, op2, op3, op4 = st.columns(4)
        with op1:
            render_card(
                "Max Sharpe — Return",
                fmt_pct(sharpe_p["return"] * 100, prec=2),
                COL_AMBER,
            )
        with op2:
            render_card(
                "Max Sharpe — Vol",
                fmt_pct(sharpe_p["volatility"] * 100, prec=2),
                COL_TEXT,
                sub=f"Sharpe {sharpe_p['sharpe']:.3f}",
            )
        with op3:
            render_card(
                "Min Vol — Return",
                fmt_pct(minvol_p["return"] * 100, prec=2),
                COL_GREEN,
            )
        with op4:
            render_card(
                "Min Vol — Vol",
                fmt_pct(minvol_p["volatility"] * 100, prec=2),
                COL_TEXT,
                sub=f"Sharpe {minvol_p['sharpe']:.3f}",
            )

        # Weights tables
        render_section("WEIGHTS")
        w1, w2 = st.columns(2)
        with w1:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; letter-spacing:1px; '
                f'text-transform:uppercase; margin-bottom:6px;">Max Sharpe</div>',
                unsafe_allow_html=True,
            )
            wdf_s = (sharpe_p["weights"] * 100).round(2).to_frame("Weight %")
            st.dataframe(style_table(wdf_s, fmt="{:.2f}"), use_container_width=True)
        with w2:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; letter-spacing:1px; '
                f'text-transform:uppercase; margin-bottom:6px;">Min Vol</div>',
                unsafe_allow_html=True,
            )
            wdf_m = (minvol_p["weights"] * 100).round(2).to_frame("Weight %")
            st.dataframe(style_table(wdf_m, fmt="{:.2f}"), use_container_width=True)

        # Returns / cov panel
        render_section("INPUTS")
        i1, i2 = st.columns(2)
        with i1:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; letter-spacing:1px; '
                f'text-transform:uppercase; margin-bottom:6px;">Expected Returns (Annualized)</div>',
                unsafe_allow_html=True,
            )
            mu_df = (mu * 100).round(2).to_frame("Return %")
            st.dataframe(style_table(mu_df, fmt="{:.2f}"), use_container_width=True)
        with i2:
            st.markdown(
                f'<div style="color:{COL_TEXT_DIM}; font-size:10px; letter-spacing:1px; '
                f'text-transform:uppercase; margin-bottom:6px;">Covariance Matrix</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(style_table(cov.round(4), fmt="{:.4f}"), use_container_width=True)

        # Efficient frontier
        render_section("EFFICIENT FRONTIER")
        with st.spinner("Building frontier..."):
            frontier = efficient_frontier(mu, cov, n_points=40, allow_short=allow_short)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=frontier["volatility"] * 100,
            y=frontier["return"] * 100,
            mode="lines",
            line=dict(color=COL_AMBER, width=1.5),
            name="Frontier",
        ))
        ind_vol = (cov.values.diagonal() ** 0.5) * 100
        fig.add_trace(go.Scatter(
            x=ind_vol, y=mu.values * 100,
            mode="markers+text",
            marker=dict(size=7, color=COL_TEXT_DIM, symbol="circle"),
            text=mu.index.tolist(),
            textposition="top center",
            textfont=dict(size=9, color=COL_TEXT_DIM),
            name="Assets",
        ))
        fig.add_trace(go.Scatter(
            x=[sharpe_p["volatility"] * 100],
            y=[sharpe_p["return"] * 100],
            mode="markers+text",
            marker=dict(size=14, color=COL_AMBER, symbol="diamond"),
            text=["MAX SHARPE"], textposition="top right",
            textfont=dict(size=9, color=COL_AMBER),
            name="Max Sharpe",
        ))
        fig.add_trace(go.Scatter(
            x=[minvol_p["volatility"] * 100],
            y=[minvol_p["return"] * 100],
            mode="markers+text",
            marker=dict(size=12, color=COL_GREEN, symbol="square"),
            text=["MIN VOL"], textposition="bottom right",
            textfont=dict(size=9, color=COL_GREEN),
            name="Min Vol",
        ))
        fig.update_xaxes(title=dict(text="Volatility (annualized %)", font=dict(size=10, color=COL_TEXT_DIM)))
        fig.update_yaxes(title=dict(text="Expected Return (annualized %)", font=dict(size=10, color=COL_TEXT_DIM)))
        fig = plotly_theme(fig, height=420)
        st.plotly_chart(fig, use_container_width=True)
