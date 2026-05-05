"""
Equity analysis — single-stock deep-dive.

Sidebar holds the WACC / DCF parameters (collapsed by default at the
session level). Main area: ticker input → header metrics → ratios table.

Note: full valuation models land in Session 3. This page wires the
ratios layer (Session 2) into the new theme.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from core.constants import DEFAULT_WACC_PARAMS, DCF_DEFAULTS
from analysis.ratios import calculate_ratios
from analysis.earnings_quality import assess_earnings_quality
from ui.components.header_metric import render_header_metric


# ============================================================
# Sidebar — WACC + DCF parameters with tooltips and reset
# ============================================================
def _wacc_sidebar() -> dict:
    with st.sidebar:
        st.markdown(
            f'<div style="color: var(--accent); font-size: 11px; '
            f'font-weight: 500; letter-spacing: 1px; text-transform: uppercase; '
            f'padding: 4px 0 8px 0; border-bottom: 1px solid var(--border); '
            f'margin-bottom: 12px;">WACC components</div>',
            unsafe_allow_html=True,
        )

        params: dict = {}
        params["beta"] = st.number_input(
            "Beta", value=1.20, step=0.10, format="%.2f",
            help="Equity beta — sensitivity to the broad market. Computed via OLS regression in production.",
        )
        params["risk_free"] = st.number_input(
            "Risk-free rate",
            value=DEFAULT_WACC_PARAMS["risk_free_rate"],
            step=0.005, format="%.3f",
            help="10Y US Treasury yield. Sourced from FRED in production.",
        )
        params["erp"] = st.number_input(
            "Equity risk premium",
            value=DEFAULT_WACC_PARAMS["market_risk_premium"],
            step=0.005, format="%.3f",
            help="Expected return of equities over the risk-free rate. Damodaran's USA value.",
        )
        params["cost_of_debt"] = st.number_input(
            "Cost of debt (pre-tax)",
            value=DEFAULT_WACC_PARAMS["cost_of_debt"],
            step=0.005, format="%.3f",
            help="Interest expense / average total debt over the last 3 years.",
        )
        params["tax_rate"] = st.number_input(
            "Tax rate",
            value=DEFAULT_WACC_PARAMS["tax_rate"],
            step=0.05, format="%.2f",
            help="Effective tax rate (3-year average).",
        )

        st.markdown(
            f'<div style="color: var(--accent); font-size: 11px; '
            f'font-weight: 500; letter-spacing: 1px; text-transform: uppercase; '
            f'padding: 4px 0 8px 0; border-bottom: 1px solid var(--border); '
            f'margin: 18px 0 12px 0;">Capital structure</div>',
            unsafe_allow_html=True,
        )
        we = st.number_input(
            "Equity %", value=DEFAULT_WACC_PARAMS["weight_equity"] * 100,
            min_value=0.0, max_value=100.0, step=5.0, format="%.1f",
            help="Equity weight in the capital structure. Use market values, not book.",
        )
        params["weight_equity"] = we / 100.0
        params["weight_debt"] = 1.0 - params["weight_equity"]

        st.markdown(
            f'<div style="color: var(--accent); font-size: 11px; '
            f'font-weight: 500; letter-spacing: 1px; text-transform: uppercase; '
            f'padding: 4px 0 8px 0; border-bottom: 1px solid var(--border); '
            f'margin: 18px 0 12px 0;">Projection</div>',
            unsafe_allow_html=True,
        )
        params["projection_years"] = st.number_input(
            "Years", value=DCF_DEFAULTS["projection_years"],
            min_value=3, max_value=10, step=1,
            help="Number of explicit projection years before terminal value.",
        )
        params["terminal_growth"] = st.number_input(
            "Terminal growth",
            value=DCF_DEFAULTS["terminal_growth"],
            step=0.005, format="%.3f",
            help="Long-run growth rate. Should not exceed nominal GDP growth (~4%).",
        )
        params["override_growth"] = st.number_input(
            "Override growth (0 = CAGR)",
            value=0.0, step=0.01, format="%.2f",
            help="Force a specific FCF growth rate. Set to 0 to use the historical CAGR.",
        )

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
        if st.button("Reset to defaults", type="secondary", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith("FormSubmitter") or k.startswith("$"):
                    continue
            st.rerun()

        return params


_ = _wacc_sidebar()


# ============================================================
# Main area
# ============================================================
st.markdown(
    '<div class="eq-section-label">EQUITY ANALYSIS</div>',
    unsafe_allow_html=True,
)

ic1, ic2, ic3 = st.columns([1.2, 3, 1])
with ic1:
    ticker = st.text_input(
        "Ticker", value="AAPL", label_visibility="collapsed",
        placeholder="TICKER",
    ).strip().upper()
with ic2:
    peers = st.text_input(
        "Peers", value="MSFT,GOOGL,META", label_visibility="collapsed",
        placeholder="PEERS (comma-separated)",
    )
with ic3:
    analyze = st.button("Analyze", use_container_width=True)


# ============================================================
# Demo mode — uses Session 2 fixtures so this page works without an
# FMP API key. Once the orchestrator lands, swap to the live provider.
# ============================================================
def _load_demo(ticker: str):
    from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023
    table = {"AAPL": aapl_fy2023, "MSFT": msft_fy2023, "JPM": jpm_fy2023}
    if ticker in table:
        m = table[ticker]
        return m.income(), m.balance(), m.cash_flow()
    return None


if analyze or "eq_loaded" in st.session_state:
    data = _load_demo(ticker)
    if data is None:
        st.info(
            f"`{ticker}` is not in the local fixture set. "
            "Live FMP fetch arrives in a later session — meanwhile try AAPL, MSFT or JPM."
        )
        st.stop()
    st.session_state["eq_loaded"] = True

    inc, bal, cf = data
    ratios = calculate_ratios(inc, bal, cf)
    eq = assess_earnings_quality(inc, bal, cf)

    last = ratios.iloc[-1]
    rev = float(last["Revenue"]) if "Revenue" in last else None
    net_margin = float(last["Net Margin %"]) if "Net Margin %" in last else None
    roic = float(last["ROIC %"]) if "ROIC %" in last else None

    h1, h2, h3, h4 = st.columns(4)
    with h1: render_header_metric("Revenue (latest)",
                                  f"${rev/1e9:,.2f}B" if rev else "—")
    with h2: render_header_metric("Net margin",
                                  f"{net_margin:.2f}%" if net_margin is not None else "—")
    with h3: render_header_metric("ROIC",
                                  f"{roic:.2f}%" if roic is not None else "—")
    with h4: render_header_metric("EQ flag", eq.overall_flag.upper())

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">FINANCIAL RATIOS</div>',
        unsafe_allow_html=True,
    )

    show_cols = [
        c for c in (
            "Gross Margin %", "Operating Margin %", "EBITDA Margin %", "Net Margin %",
            "ROE %", "ROA %", "ROIC %",
            "Debt/Equity", "Current Ratio",
            "FCF Margin %", "FCF Adj Margin %", "Cash Conversion",
        ) if c in ratios.columns
    ]
    transposed = ratios[show_cols].T
    transposed.columns = [d.strftime("%Y") if hasattr(d, "strftime") else str(d)
                          for d in transposed.columns]
    st.dataframe(transposed.round(2), use_container_width=True, height=440)

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">EARNINGS QUALITY</div>',
        unsafe_allow_html=True,
    )
    flags = [f for f in (eq.beneish, eq.piotroski, eq.sloan) if f is not None]
    if flags:
        rows = pd.DataFrame([{
            "Metric": f.name,
            "Score": f.score,
            "Flag": f.flag.upper(),
            "Explanation": f.explanation,
        } for f in flags])
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Score": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    st.caption(
        "Valuation models (DCF 3-stage, Monte Carlo, comparables, RI, DDM) "
        "land in Session 3."
    )
else:
    st.markdown(
        '<div class="eq-card" style="text-align:center; padding:48px 16px; '
        'color:var(--text-muted);">Enter a ticker and press Analyze.</div>',
        unsafe_allow_html=True,
    )
