"""
Equity analysis — single-stock deep-dive.

Sidebar is no longer used for WACC; instead, the **ASSUMPTIONS** panel
(an inline expander) lives between the header metrics and the valuation
section. All five valuation models, the aggregator, the score and the
final rating run through ``core.valuation_pipeline.run_valuation`` so
that any change to an assumption automatically re-runs everything.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from analysis.assumptions import (
    Assumptions, calculate_default_assumptions,
)
from analysis.ratios import calculate_ratios
from analysis.earnings_quality import assess_earnings_quality
from core.exceptions import ValuationError, InsufficientDataError
from core.valuation_pipeline import run_valuation
from data.ticker_universe import SP500_TOP, labels as ticker_labels, ticker_from_label
from data.user_assumptions_db import (
    save_assumptions, load_assumptions_with_meta, delete_assumptions,
    IS_PERSISTENT,
)
from valuation.comparables import PeerSnapshot, comparables_table
from valuation.dcf_three_stage import sensitivity_table
from ui.components.header_metric import render_header_metric
from ui.components.valuation_card import render_valuation_card
from ui.components.score_breakdown import render_rating_pill, render_score_breakdown
from ui.components.monte_carlo_chart import build_mc_distribution_figure
from ui.components.assumptions_panel import render_assumptions_panel


# ============================================================
# Demo fixtures + curated metadata
# ============================================================
def _load_demo(ticker: str):
    from tests.fixtures import aapl_fy2023, msft_fy2023, jpm_fy2023
    table = {"AAPL": aapl_fy2023, "MSFT": msft_fy2023, "JPM": jpm_fy2023}
    if ticker in table:
        m = table[ticker]
        return m.income(), m.balance(), m.cash_flow()
    return None


_DEMO_PEERS: dict[str, list[PeerSnapshot]] = {
    "AAPL": [
        PeerSnapshot("MSFT",  market_cap=2_900e9, enterprise_value=2_950e9,
                     net_income=72.4e9,  revenue=211.9e9, ebitda=102.4e9, book_value=206.2e9),
        PeerSnapshot("GOOGL", market_cap=1_800e9, enterprise_value=1_750e9,
                     net_income=73.8e9,  revenue=307.4e9, ebitda=95.4e9,  book_value=283.4e9),
        PeerSnapshot("META",  market_cap=1_100e9, enterprise_value=1_080e9,
                     net_income=39.1e9,  revenue=134.9e9, ebitda=70.2e9,  book_value=153.2e9),
        PeerSnapshot("NVDA",  market_cap=2_300e9, enterprise_value=2_290e9,
                     net_income=29.8e9,  revenue=60.9e9,  ebitda=37.1e9,  book_value=43.0e9),
    ],
    "MSFT": [
        PeerSnapshot("AAPL",  market_cap=2_950e9, enterprise_value=3_030e9,
                     net_income=97.0e9,  revenue=383.3e9, ebitda=129.6e9, book_value=62.1e9),
        PeerSnapshot("GOOGL", market_cap=1_800e9, enterprise_value=1_750e9,
                     net_income=73.8e9,  revenue=307.4e9, ebitda=95.4e9,  book_value=283.4e9),
        PeerSnapshot("META",  market_cap=1_100e9, enterprise_value=1_080e9,
                     net_income=39.1e9,  revenue=134.9e9, ebitda=70.2e9,  book_value=153.2e9),
        PeerSnapshot("ORCL",  market_cap=350e9,   enterprise_value=440e9,
                     net_income=10.5e9,  revenue=50.0e9,  ebitda=20.4e9,  book_value=1.6e9),
    ],
    "JPM": [
        PeerSnapshot("BAC", market_cap=270e9, net_income=26.5e9, revenue=171.9e9, book_value=291.6e9),
        PeerSnapshot("WFC", market_cap=200e9, net_income=19.1e9, revenue=82.6e9,  book_value=187.4e9),
        PeerSnapshot("C",   market_cap=130e9, net_income=9.2e9,  revenue=78.5e9,  book_value=205.5e9),
        PeerSnapshot("GS",  market_cap=160e9, net_income=8.5e9,  revenue=46.3e9,  book_value=117.0e9),
        PeerSnapshot("MS",  market_cap=180e9, net_income=9.1e9,  revenue=54.1e9,  book_value=99.9e9),
    ],
}

_DEMO_PRICE: dict[str, float] = {"AAPL": 185.0, "MSFT": 330.0, "JPM": 160.0}
_DEMO_MARKET_CAP: dict[str, float] = {"AAPL": 2_950e9, "MSFT": 2_460e9, "JPM": 470e9}
_DEMO_SECTOR: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JPM":  "Financial Services",
}


# ============================================================
# Page header — ticker selector
# ============================================================
st.markdown(
    '<div class="eq-section-label">EQUITY ANALYSIS</div>',
    unsafe_allow_html=True,
)

_LABELS: list[str] = ticker_labels(SP500_TOP)

lab1, lab2, lab3, lab4 = st.columns([0.9, 4.0, 2.0, 1.1])
with lab1: st.markdown('<div class="eq-section-label">MODE</div>', unsafe_allow_html=True)
with lab2: st.markdown('<div class="eq-section-label">TICKER</div>', unsafe_allow_html=True)
with lab3: st.markdown('<div class="eq-section-label">PEERS</div>', unsafe_allow_html=True)
with lab4: st.markdown('<div class="eq-section-label">&nbsp;</div>', unsafe_allow_html=True)

ic1, ic2, ic3, ic4 = st.columns([0.9, 4.0, 2.0, 1.1])
with ic1:
    use_custom = st.toggle(
        "Custom", value=False,
        help="Toggle on to type any ticker outside the curated S&P 500 list.",
    )
with ic2:
    if use_custom:
        ticker = st.text_input(
            "Ticker", value="AAPL", label_visibility="collapsed",
            placeholder="Type a ticker (e.g. AAPL)",
        ).strip().upper()
    else:
        default_idx = next(
            (i for i, lbl in enumerate(_LABELS) if lbl.startswith("AAPL ")),
            0,
        )
        chosen_label = st.selectbox(
            "Ticker", options=_LABELS, index=default_idx,
            label_visibility="collapsed",
            placeholder="🔎  Search ticker or company…",
        )
        ticker = ticker_from_label(chosen_label)
with ic3:
    peers_raw = st.text_input(
        "Peers", value="MSFT,GOOGL,META",
        label_visibility="collapsed",
        placeholder="Comma-separated",
    )
with ic4:
    analyze = st.button("Analyze", type="primary", use_container_width=True)


# ============================================================
# Main flow
# ============================================================
if analyze:
    st.session_state["eq_active_ticker"] = ticker

active_ticker: str | None = st.session_state.get("eq_active_ticker")

if active_ticker is None:
    st.markdown(
        '<div class="eq-card" style="text-align:center; padding:48px 16px; '
        'color:var(--text-muted);">Pick a ticker and press Analyze.</div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ---- Load financials (demo only for now) ----
data = _load_demo(active_ticker)
if data is None:
    st.info(
        f"`{active_ticker}` is not in the local fixture set. "
        "Live FMP fetch arrives in a later session — meanwhile try AAPL, MSFT or JPM."
    )
    st.stop()

inc, bal, cf = data
ratios = calculate_ratios(inc, bal, cf)
eq = assess_earnings_quality(inc, bal, cf)


# ============================================================
# Header metrics
# ============================================================
last = ratios.iloc[-1]
rev = float(last["Revenue"]) if "Revenue" in last else None
net_margin = float(last["Net Margin %"]) if "Net Margin %" in last else None
roic = float(last["ROIC %"]) if "ROIC %" in last else None
current_price = _DEMO_PRICE.get(active_ticker)

h1, h2, h3, h4 = st.columns(4)
with h1: render_header_metric("Revenue (latest)", f"${rev/1e9:,.2f}B" if rev else "—")
with h2: render_header_metric("Net margin",       f"{net_margin:.2f}%" if net_margin is not None else "—")
with h3: render_header_metric("ROIC",             f"{roic:.2f}%" if roic is not None else "—")
with h4: render_header_metric("EQ flag",          eq.overall_flag.upper())


# ============================================================
# ASSUMPTIONS panel — replaces the old WACC sidebar
# ============================================================
st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

base_assumptions: Assumptions = calculate_default_assumptions(
    income=inc, balance=bal, cash=cf,
    beta_override=1.20,
    market_cap=_DEMO_MARKET_CAP.get(active_ticker),
)

# Offer to load any saved custom assumptions on the first visit per session.
saved_meta = load_assumptions_with_meta(active_ticker)
loaded_offered_key = f"_load_offered_{active_ticker}"
if saved_meta is not None and loaded_offered_key not in st.session_state:
    st.session_state[loaded_offered_key] = True
    saved_params, saved_ts = saved_meta
    try:
        ts_pretty = datetime.fromisoformat(saved_ts).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        ts_pretty = saved_ts

    cl, cr1, cr2 = st.columns([3, 1, 1])
    with cl:
        st.info(
            f"You have saved custom assumptions for **{active_ticker}** "
            f"from **{ts_pretty}**.",
            icon="💾",
        )
    with cr1:
        if st.button("Load saved", key=f"load_saved_{active_ticker}",
                     use_container_width=True):
            st.session_state[f"assumptions_{active_ticker}_user"] = saved_params
            st.session_state[f"preset_{active_ticker}"] = "Custom"
            st.rerun()
    with cr2:
        if st.button("Discard", key=f"discard_saved_{active_ticker}",
                     type="secondary", use_container_width=True):
            delete_assumptions(active_ticker)
            del st.session_state[loaded_offered_key]
            st.rerun()

if not IS_PERSISTENT:
    st.caption(
        "⚠ Assumptions DB is on a non-persistent path — "
        "saves last only for the current Streamlit session."
    )

assumptions: Assumptions = render_assumptions_panel(
    ticker=active_ticker,
    base=base_assumptions,
    expanded=(f"_panel_visited_{active_ticker}" not in st.session_state),
    on_save=lambda a: save_assumptions(active_ticker, a.to_dict()),
    on_reset=lambda: delete_assumptions(active_ticker),
)
st.session_state[f"_panel_visited_{active_ticker}"] = True

if base_assumptions.warnings:
    with st.expander("ℹ Default-derivation notes", expanded=False):
        for w in base_assumptions.warnings:
            st.markdown(f"- {w}")


# ============================================================
# Valuation pipeline (re-runs on every assumption change)
# ============================================================
peers_demo = _DEMO_PEERS.get(active_ticker, [])
sector = _DEMO_SECTOR.get(active_ticker)

with st.spinner("Running valuation pipeline…"):
    try:
        results = run_valuation(
            ticker=active_ticker,
            income=inc, balance=bal, cash=cf,
            assumptions=assumptions,
            peers=peers_demo,
            earnings_quality=eq,
            current_price=current_price,
            sector=sector,
        )
    except (ValuationError, InsufficientDataError) as exc:
        st.error(f"Valuation pipeline failed: {exc}")
        st.stop()


# ============================================================
# Section: rating + aggregator + score breakdown
# ============================================================
st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">VALUATION</div>',
    unsafe_allow_html=True,
)

rp1, rp2 = st.columns([3, 2])
with rp1:
    render_rating_pill(results.rating)
with rp2:
    if np.isfinite(results.aggregator.intrinsic_per_share):
        render_valuation_card(
            model=f"AGGREGATOR · {results.aggregator.profile.upper()}",
            intrinsic=results.aggregator.intrinsic_per_share,
            current_price=current_price,
            range_low=results.aggregator.range_low,
            range_high=results.aggregator.range_high,
            sub_label=(
                f"{results.aggregator.n_models_used} models · "
                f"CV {results.aggregator.dispersion_cv:.1%} · "
                f"confidence {results.aggregator.confidence}"
            ),
        )
    else:
        st.warning("No model produced a valid intrinsic estimate.")

st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
render_score_breakdown(results.score)


# ============================================================
# Per-model contribution cards
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">MODEL CONTRIBUTIONS</div>',
    unsafe_allow_html=True,
)

vc1, vc2, vc3, vc4 = st.columns(4)
with vc1:
    if results.dcf is not None:
        render_valuation_card(
            model="DCF · 3-stage",
            intrinsic=results.dcf.intrinsic_value_per_share,
            current_price=current_price,
            sub_label=(f"WACC {results.dcf.wacc:.1%} · g₁ {results.dcf.stage1_growth:.1%} "
                       f"→ g_t {results.dcf.terminal_growth:.1%}"),
        )
    else:
        render_valuation_card(model="DCF · 3-stage", intrinsic=None,
                              sub_label=results.dcf_error or "unavailable")

with vc2:
    cmp_res = results.comparables
    if cmp_res is not None and cmp_res.implied_per_share_median is not None:
        mults_used = ", ".join(cmp_res.multiples.keys())
        render_valuation_card(
            model="COMPARABLES",
            intrinsic=cmp_res.implied_per_share_median,
            current_price=current_price,
            range_low=cmp_res.implied_per_share_low,
            range_high=cmp_res.implied_per_share_high,
            sub_label=f"{cmp_res.n_peers_input} peers · {mults_used}",
        )
    else:
        render_valuation_card(model="COMPARABLES", intrinsic=None,
                              sub_label=results.comparables_error or "no peers")

with vc3:
    if results.monte_carlo is not None:
        mc = results.monte_carlo
        render_valuation_card(
            model="MONTE CARLO",
            intrinsic=mc.median,
            current_price=current_price,
            range_low=mc.percentiles.get(25),
            range_high=mc.percentiles.get(75),
            sub_label=(f"{mc.n_simulations:,} sims · "
                       f"P(undervalued) {mc.p_undervalued:.0%}"
                       if mc.p_undervalued is not None
                       else f"{mc.n_simulations:,} sims"),
        )
    else:
        render_valuation_card(model="MONTE CARLO", intrinsic=None,
                              sub_label=results.monte_carlo_error or "unavailable")

with vc4:
    if results.ddm is not None:
        d = results.ddm
        render_valuation_card(
            model="DDM · 2-stage",
            intrinsic=d.intrinsic_value_per_share,
            current_price=current_price,
            sub_label=(f"DPS ${d.base_dividend:.2f} · g₁ {d.stage1_growth:.1%} · "
                       f"payout {d.payout_ratio:.0%}"
                       if d.payout_ratio is not None
                       else f"DPS ${d.base_dividend:.2f}"),
        )
    elif results.residual_income is not None:
        ri = results.residual_income
        render_valuation_card(
            model="RESIDUAL INCOME",
            intrinsic=ri.intrinsic_value_per_share,
            current_price=current_price,
            sub_label=(f"BV/sh ${ri.book_value_per_share:.2f} · "
                       f"ROE {ri.base_roe:.1%}"),
        )
    else:
        render_valuation_card(model="DDM / RI", intrinsic=None,
                              sub_label="not applicable")


# ============================================================
# Detail tables
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">FINANCIAL RATIOS</div>',
    unsafe_allow_html=True,
)
show_cols = [c for c in (
    "Gross Margin %", "Operating Margin %", "EBITDA Margin %", "Net Margin %",
    "ROE %", "ROA %", "ROIC %",
    "Debt/Equity", "Current Ratio",
    "FCF Margin %", "FCF Adj Margin %", "Cash Conversion",
) if c in ratios.columns]
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
        "Metric": f.name, "Score": f.score,
        "Flag": f.flag.upper(), "Explanation": f.explanation,
    } for f in flags])
    st.dataframe(
        rows, hide_index=True, use_container_width=True,
        column_config={"Score": st.column_config.NumberColumn(format="%.2f")},
    )


# ---- DCF projection + EV split ----
if results.dcf is not None:
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">DCF — FCF PROJECTION (USD MM)</div>',
        unsafe_allow_html=True,
    )
    dcf = results.dcf
    proj = pd.DataFrame({
        "Year":     [f"Y{i+1}" for i in range(len(dcf.projected_fcf))],
        "Growth":   [f"{g*100:.2f}%" for g in dcf.growth_path],
        "FCF":      [v / 1e6 for v in dcf.projected_fcf],
        "Discount": [f"{d:.4f}" for d in dcf.discount_factors],
        "PV":       [v / 1e6 for v in dcf.pv_per_year],
    })
    st.dataframe(
        proj, hide_index=True, use_container_width=True,
        column_config={
            "FCF": st.column_config.NumberColumn(format="%.0f"),
            "PV":  st.column_config.NumberColumn(format="%.0f"),
        },
    )
    ev_split = pd.DataFrame([{
        "Component": "PV of explicit FCF",
        "USD (B)":     dcf.pv_explicit / 1e9,
        "Share of EV": dcf.pv_explicit / dcf.enterprise_value * 100,
    }, {
        "Component": "PV of terminal value",
        "USD (B)":     dcf.pv_terminal / 1e9,
        "Share of EV": dcf.pv_terminal / dcf.enterprise_value * 100,
    }])
    st.dataframe(
        ev_split, hide_index=True, use_container_width=True,
        column_config={
            "USD (B)":     st.column_config.NumberColumn(format="%.2f"),
            "Share of EV": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    # ---- Sensitivity table ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">SENSITIVITY · INTRINSIC $/SHARE</div>',
        unsafe_allow_html=True,
    )
    wacc_grid = [round(results.wacc.wacc + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    g_grid    = [round(assumptions.terminal_growth + d, 4)
                 for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    g_override = assumptions.override_growth or None
    sens = sensitivity_table(
        income=inc, balance=bal, cash=cf,
        wacc_grid=wacc_grid, g_grid=g_grid,
        stage1_growth=g_override,
    )
    sens.index   = [f"{w:.2%}" for w in sens.index]
    sens.columns = [f"{g:.2%}" for g in sens.columns]
    sens.index.name = "WACC ↓ / g →"
    st.dataframe(sens.round(2), use_container_width=True)


# ---- Comparables breakdown ----
if results.comparables is not None and results.comparables.multiples:
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">COMPARABLES BREAKDOWN</div>',
        unsafe_allow_html=True,
    )
    tbl = comparables_table(results.comparables)
    st.dataframe(
        tbl, hide_index=True, use_container_width=True,
        column_config={
            "Median":          st.column_config.NumberColumn(format="%.2f"),
            "P25":             st.column_config.NumberColumn(format="%.2f"),
            "P75":             st.column_config.NumberColumn(format="%.2f"),
            "Implied $/share": st.column_config.NumberColumn(format="$%.2f"),
        },
    )


# ---- Monte Carlo distribution ----
if results.monte_carlo is not None:
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">MONTE CARLO · INTRINSIC VALUE DISTRIBUTION</div>',
        unsafe_allow_html=True,
    )
    mc = results.monte_carlo
    st.plotly_chart(
        build_mc_distribution_figure(
            mc.intrinsic_distribution,
            percentiles=mc.percentiles,
            current_price=current_price,
        ),
        use_container_width=True, config={"displayModeBar": False},
    )
    mc_summary = pd.DataFrame([
        {"Statistic": "Mean",    "Value": f"${mc.mean:,.2f}"},
        {"Statistic": "Median",  "Value": f"${mc.median:,.2f}"},
        {"Statistic": "Std dev", "Value": f"${mc.std:,.2f}"},
        *[
            {"Statistic": f"Percentile {p}", "Value": f"${v:,.2f}"}
            for p, v in mc.percentiles.items()
        ],
        {"Statistic": "Sims that failed validation",
         "Value": f"{mc.n_failed:,} / {mc.n_simulations:,}"},
    ])
    st.dataframe(mc_summary, hide_index=True, use_container_width=True)

st.caption(
    "Demo peer set; FMP screener replaces it once the live provider is online. "
    "Save assumptions per-ticker via the panel above."
)
