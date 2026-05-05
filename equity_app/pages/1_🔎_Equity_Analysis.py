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

import numpy as np
import pandas as pd
import streamlit as st

from core.constants import DEFAULT_WACC_PARAMS, DCF_DEFAULTS
from core.exceptions import ValuationError, InsufficientDataError
from analysis.ratios import calculate_ratios
from analysis.earnings_quality import assess_earnings_quality
from analysis.wacc import calculate_wacc
from valuation.dcf_three_stage import run_dcf, sensitivity_table
from valuation.comparables import (
    PeerSnapshot, TargetFundamentals,
    value_by_comparables, comparables_table,
)
from valuation.monte_carlo import run_monte_carlo
from valuation.ddm import two_stage as ddm_two_stage, is_applicable as ddm_is_applicable
from valuation.residual_income import run_residual_income
from valuation.valuation_aggregator import aggregate
from scoring.scorer import compute_score
from scoring.rating import rate
from ui.components.header_metric import render_header_metric
from ui.components.valuation_card import render_valuation_card
from ui.components.score_breakdown import render_rating_pill, render_score_breakdown
from ui.components.monte_carlo_chart import build_mc_distribution_figure


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


params = _wacc_sidebar()


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


# Hand-curated demo peer snapshots (USD, FY2023). Replaced by the FMP
# screener once the live provider is wired in.
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

# Approximate prices around the fiscal year end — used to compute upside.
_DEMO_PRICE: dict[str, float] = {"AAPL": 185.0, "MSFT": 330.0, "JPM": 160.0}

# DCF on FCFF doesn't apply to banks (no meaningful FCF). Skip cleanly.
_NO_DCF: set[str] = {"JPM"}

# GICS sector per demo ticker — drives the aggregator's model weights.
_DEMO_SECTOR: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JPM":  "Financial Services",
}


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

    # ============================================================
    # VALUATION — DCF + comparables
    # ============================================================
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">VALUATION</div>',
        unsafe_allow_html=True,
    )

    try:
        wacc_res = calculate_wacc(
            risk_free=params["risk_free"],
            equity_risk_premium=params["erp"],
            beta=params["beta"],
            cost_of_debt_pretax=params["cost_of_debt"],
            tax_rate=params["tax_rate"],
            weight_equity=params["weight_equity"],
            weight_debt=params["weight_debt"],
        )
    except ValuationError as exc:
        st.error(f"WACC inputs invalid: {exc}")
        st.stop()

    current_price = _DEMO_PRICE.get(ticker)
    g_override = params["override_growth"] or None  # 0 ⇒ use historical CAGR

    # ---- DCF card + projection ----
    dcf_res = None
    dcf_error: str | None = None
    if ticker not in _NO_DCF:
        try:
            dcf_res = run_dcf(
                income=inc, balance=bal, cash=cf,
                wacc=wacc_res.wacc,
                stage1_growth=g_override,
                stage1_years=params["projection_years"],
                terminal_growth=params["terminal_growth"],
            )
        except (ValuationError, InsufficientDataError) as exc:
            dcf_error = str(exc)

    # ---- Comparables card ----
    cmp_res = None
    cmp_error: str | None = None
    peers_demo = _DEMO_PEERS.get(ticker, [])
    if peers_demo:
        last_inc = inc.iloc[-1]
        last_bal = bal.iloc[-1]

        def _pick(row, *keys):
            for k in keys:
                if k in row and pd.notna(row[k]):
                    return float(row[k])
            return None

        target_fund = TargetFundamentals(
            net_income=_pick(last_inc, "netIncome"),
            revenue=_pick(last_inc, "revenue"),
            ebitda=_pick(last_inc, "ebitda"),
            book_value=_pick(last_bal, "totalStockholdersEquity"),
            shares_outstanding=_pick(last_inc, "weightedAverageShsOut"),
            cash=_pick(last_bal, "cashAndCashEquivalents") or 0.0,
            debt=_pick(last_bal, "totalDebt") or 0.0,
        )
        try:
            cmp_res = value_by_comparables(peers=peers_demo, target=target_fund)
        except (ValuationError, InsufficientDataError) as exc:
            cmp_error = str(exc)

    # ---- Monte Carlo (wraps DCF, so skip if no DCF) ----
    mc_res = None
    if dcf_res is not None:
        try:
            with st.spinner("Running 5,000 Monte Carlo simulations…"):
                mc_res = run_monte_carlo(
                    income=inc, balance=bal, cash=cf,
                    wacc=wacc_res.wacc,
                    n_simulations=5_000,
                    current_price=current_price,
                    stage1_years=params["projection_years"],
                    seed=42,
                )
        except (ValuationError, InsufficientDataError):
            mc_res = None

    # ---- DDM (only if the company actually pays dividends) ----
    ddm_res = None
    if ddm_is_applicable(cf, inc):
        try:
            ddm_res = ddm_two_stage(
                income=inc, balance=bal, cash=cf,
                cost_of_equity=wacc_res.cost_of_equity,
                stage1_years=params["projection_years"],
                terminal_growth=params["terminal_growth"],
            )
        except (ValuationError, InsufficientDataError):
            ddm_res = None

    # ---- Residual Income ----
    ri_res = None
    try:
        ri_res = run_residual_income(
            income=inc, balance=bal,
            cost_of_equity=wacc_res.cost_of_equity,
            stage1_years=params["projection_years"],
            stage1_growth=g_override,
            terminal_growth=params["terminal_growth"],
        )
    except (ValuationError, InsufficientDataError):
        ri_res = None

    # ---- Aggregate the 5 estimates with sector weights ----
    sector = _DEMO_SECTOR.get(ticker)
    agg = aggregate(
        dcf=dcf_res.intrinsic_value_per_share if dcf_res else None,
        comparables=(cmp_res.implied_per_share_median
                     if cmp_res and cmp_res.implied_per_share_median else None),
        monte_carlo=mc_res.median if mc_res else None,
        ddm=ddm_res.intrinsic_value_per_share if ddm_res else None,
        residual_income=ri_res.intrinsic_value_per_share if ri_res else None,
        sector=sector,
    )

    # ---- Composite score + final rating ----
    upside = None
    if (np.isfinite(agg.intrinsic_per_share)
            and current_price and current_price > 0):
        upside = (agg.intrinsic_per_share - current_price) / current_price

    score_res = compute_score(
        income=inc, balance=bal, cash=cf,
        earnings_quality=eq,
        intrinsic=agg.intrinsic_per_share if np.isfinite(agg.intrinsic_per_share) else None,
        current_price=current_price,
    )
    rating_res = rate(
        composite=score_res.composite,
        upside=upside,
        confidence=agg.confidence,
    )

    # ---- Render: rating pill + score breakdown side-by-side ----
    rp1, rp2 = st.columns([3, 2])
    with rp1:
        render_rating_pill(rating_res)
    with rp2:
        if np.isfinite(agg.intrinsic_per_share):
            render_valuation_card(
                model=f"AGGREGATOR · {agg.profile.upper()}",
                intrinsic=agg.intrinsic_per_share,
                current_price=current_price,
                range_low=agg.range_low,
                range_high=agg.range_high,
                sub_label=(
                    f"{agg.n_models_used} models · CV {agg.dispersion_cv:.1%} · "
                    f"confidence {agg.confidence}"
                ),
            )
        else:
            st.warning("No model produced a valid intrinsic estimate.")

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    render_score_breakdown(score_res)

    # ---- Per-model cards (DCF · Comps · MC · DDM/RI) ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">MODEL CONTRIBUTIONS</div>',
        unsafe_allow_html=True,
    )
    vc1, vc2, vc3, vc4 = st.columns(4)

    with vc1:
        if dcf_res is not None:
            render_valuation_card(
                model="DCF · 3-stage",
                intrinsic=dcf_res.intrinsic_value_per_share,
                current_price=current_price,
                sub_label=(f"WACC {dcf_res.wacc:.1%} · g₁ {dcf_res.stage1_growth:.1%} "
                           f"→ g_t {dcf_res.terminal_growth:.1%}"),
            )
        elif ticker in _NO_DCF:
            render_valuation_card(model="DCF · 3-stage", intrinsic=None,
                                  sub_label="N/A — bank, use DDM/RI.")
        else:
            render_valuation_card(model="DCF · 3-stage", intrinsic=None,
                                  sub_label=dcf_error or "unavailable")

    with vc2:
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
                                  sub_label=cmp_error or "no peers")

    with vc3:
        if mc_res is not None:
            render_valuation_card(
                model="MONTE CARLO",
                intrinsic=mc_res.median,
                current_price=current_price,
                range_low=mc_res.percentiles.get(25),
                range_high=mc_res.percentiles.get(75),
                sub_label=(f"{mc_res.n_simulations:,} sims · "
                           f"P(undervalued) {mc_res.p_undervalued:.0%}"
                           if mc_res.p_undervalued is not None
                           else f"{mc_res.n_simulations:,} sims"),
            )
        else:
            render_valuation_card(model="MONTE CARLO", intrinsic=None,
                                  sub_label="requires DCF")

    with vc4:
        if ddm_res is not None:
            render_valuation_card(
                model="DDM · 2-stage",
                intrinsic=ddm_res.intrinsic_value_per_share,
                current_price=current_price,
                sub_label=(f"DPS ${ddm_res.base_dividend:.2f} · "
                           f"g₁ {ddm_res.stage1_growth:.1%} · "
                           f"payout {ddm_res.payout_ratio:.0%}"
                           if ddm_res.payout_ratio is not None
                           else f"DPS ${ddm_res.base_dividend:.2f}"),
            )
        elif ri_res is not None:
            render_valuation_card(
                model="RESIDUAL INCOME",
                intrinsic=ri_res.intrinsic_value_per_share,
                current_price=current_price,
                sub_label=(f"BV/sh ${ri_res.book_value_per_share:.2f} · "
                           f"ROE {ri_res.base_roe:.1%}"),
            )
        else:
            render_valuation_card(model="DDM / RI", intrinsic=None,
                                  sub_label="not applicable")

    # ---- DCF projection table ----
    if dcf_res is not None:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">DCF — FCF PROJECTION (USD MM)</div>',
            unsafe_allow_html=True,
        )
        proj = pd.DataFrame({
            "Year":      [f"Y{i+1}" for i in range(len(dcf_res.projected_fcf))],
            "Growth":    [f"{g*100:.2f}%" for g in dcf_res.growth_path],
            "FCF":       [v / 1e6 for v in dcf_res.projected_fcf],
            "Discount":  [f"{d:.4f}" for d in dcf_res.discount_factors],
            "PV":        [v / 1e6 for v in dcf_res.pv_per_year],
        })
        st.dataframe(
            proj,
            hide_index=True,
            use_container_width=True,
            column_config={
                "FCF": st.column_config.NumberColumn(format="%.0f"),
                "PV":  st.column_config.NumberColumn(format="%.0f"),
            },
        )
        ev_split = pd.DataFrame([{
            "Component":            "PV of explicit FCF",
            "USD (B)":              dcf_res.pv_explicit / 1e9,
            "Share of EV":          dcf_res.pv_explicit / dcf_res.enterprise_value * 100,
        }, {
            "Component":            "PV of terminal value",
            "USD (B)":              dcf_res.pv_terminal / 1e9,
            "Share of EV":          dcf_res.pv_terminal / dcf_res.enterprise_value * 100,
        }])
        st.dataframe(
            ev_split, hide_index=True, use_container_width=True,
            column_config={
                "USD (B)":     st.column_config.NumberColumn(format="%.2f"),
                "Share of EV": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    # ---- Sensitivity table ----
    if dcf_res is not None:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">SENSITIVITY · INTRINSIC $/SHARE</div>',
            unsafe_allow_html=True,
        )
        wacc_grid = [round(wacc_res.wacc + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
        g_grid    = [round(params["terminal_growth"] + d, 4)
                     for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
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
    if cmp_res is not None and cmp_res.multiples:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">COMPARABLES BREAKDOWN</div>',
            unsafe_allow_html=True,
        )
        tbl = comparables_table(cmp_res)
        st.dataframe(
            tbl, hide_index=True, use_container_width=True,
            column_config={
                "Median":          st.column_config.NumberColumn(format="%.2f"),
                "P25":             st.column_config.NumberColumn(format="%.2f"),
                "P75":             st.column_config.NumberColumn(format="%.2f"),
                "Implied $/share": st.column_config.NumberColumn(format="$%.2f"),
            },
        )

    # ---- Monte Carlo distribution chart ----
    if mc_res is not None:
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">MONTE CARLO · INTRINSIC VALUE DISTRIBUTION</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            build_mc_distribution_figure(
                mc_res.intrinsic_distribution,
                percentiles=mc_res.percentiles,
                current_price=current_price,
            ),
            use_container_width=True, config={"displayModeBar": False},
        )
        mc_summary = pd.DataFrame([
            {"Statistic": "Mean",     "Value": f"${mc_res.mean:,.2f}"},
            {"Statistic": "Median",   "Value": f"${mc_res.median:,.2f}"},
            {"Statistic": "Std dev",  "Value": f"${mc_res.std:,.2f}"},
            *[
                {"Statistic": f"Percentile {p}", "Value": f"${v:,.2f}"}
                for p, v in mc_res.percentiles.items()
            ],
            {"Statistic": "Sims that failed validation",
             "Value": f"{mc_res.n_failed:,} / {mc_res.n_simulations:,}"},
        ])
        st.dataframe(mc_summary, hide_index=True, use_container_width=True)

    st.caption(
        "Demo peer set; FMP screener replaces it once the live provider is online. "
        "DDM only fires for tickers with a payout ratio ≥ 20%; non-payers fall back to RI."
    )
else:
    st.markdown(
        '<div class="eq-card" style="text-align:center; padding:48px 16px; '
        'color:var(--text-muted);">Enter a ticker and press Analyze.</div>',
        unsafe_allow_html=True,
    )
