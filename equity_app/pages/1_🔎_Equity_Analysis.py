"""
Equity analysis — single-stock deep-dive.

Page layout (top → bottom):
    1. Inputs row     — ticker search + peers + Analyze
    2. Big header     — ticker / company / sector + current price +
                        aggregator intrinsic + rating verdict + confidence
    3. Quick metrics  — 4 native st.metric cards (Revenue, Net Margin,
                        ROIC, EQ flag)
    4. Tabs           — Overview · Valuation · Financials · Quality ·
                        Peers · Charts
    5. Assumptions    — collapsed expander with preset selector. Edits
                        recompute the entire pipeline above.
    6. Footer         — disclaimer + save / export hooks
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

from analysis.assumptions import Assumptions, calculate_default_assumptions
from analysis.ratios import calculate_ratios
from analysis.earnings_quality import assess_earnings_quality
from core.exceptions import ValuationError, InsufficientDataError
from core.valuation_pipeline import run_valuation
from data.constituents import META as TICKER_META
from data.ticker_universe import (
    SP500_TOP, labels as ticker_labels, ticker_from_label,
)
from data.user_assumptions_db import (
    save_assumptions, load_assumptions_with_meta, delete_assumptions,
    IS_PERSISTENT,
)
from valuation.comparables import PeerSnapshot, comparables_table
from valuation.dcf_three_stage import sensitivity_table
from ui.charts.margins_evolution import build_margins_figure
from ui.charts.revenue_history import build_revenue_figure
from ui.components.assumptions_panel import render_assumptions_panel
from ui.components.financial_chart import (
    build_income_chart, build_balance_chart, build_fcf_chart,
)
from ui.components.financial_table import (
    render_income_statement, render_balance_sheet, render_cash_flow,
)
from ui.components.monte_carlo_chart import build_mc_distribution_figure
from ui.components.quick_metrics import render_quick_metrics
from ui.components.score_breakdown import render_score_breakdown
from ui.components.ticker_header import render_ticker_header
from ui.components.valuation_card import render_valuation_card
from ui.components.valuation_summary import render_valuation_summary


# ============================================================
# Demo data (fixtures + curated metadata)
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
_DEMO_DAILY_PCT: dict[str, float] = {"AAPL": 1.18, "MSFT": -0.42, "JPM": 0.85}
_DEMO_W52: dict[str, tuple[float, float]] = {
    "AAPL": (164.0, 198.0), "MSFT": (275.0, 372.0), "JPM": (135.0, 172.0),
}
_DEMO_MARKET_CAP: dict[str, float] = {"AAPL": 2_950e9, "MSFT": 2_460e9, "JPM": 470e9}
_DEMO_SECTOR: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JPM":  "Financial Services",
}


# ============================================================
# Landing-state vs analysis-state branching
#
# When no ticker has been analysed yet (or the user clicked
# "Back to home"), render the landing: hero searchbox · market pulse
# strip · 2x2 grid (watchlist / recently / trending / popular) +
# educational cards. The analysis pipeline runs ONLY when a ticker is
# active.
# ============================================================
from data.watchlist_db import (
    push_recent, list_watchlist, is_in_watchlist,
    add_to_watchlist, remove_from_watchlist,
)
from ui.components.landing_hero import render_landing_hero
from ui.components.market_pulse_strip import render_market_pulse_strip
from ui.components.landing_grid import render_landing_grid
from ui.components.educational_cards import render_educational_cards


def _set_active(t: str) -> None:
    """Wire callback for any landing-card click — flips into analysis state."""
    st.session_state["eq_active_ticker"] = t.upper()
    push_recent(t.upper())


active_ticker: str | None = st.session_state.get("eq_active_ticker")

# ---- LANDING STATE ----
if active_ticker is None:
    picked = render_landing_hero(key="landing_searchbox")
    if picked:
        _set_active(picked)
        st.rerun()

    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">MARKET PULSE</div>',
        unsafe_allow_html=True,
    )
    render_market_pulse_strip()

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    render_landing_grid(on_select=_set_active)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    render_educational_cards()
    st.stop()


# ============================================================
# ANALYSIS STATE — toolbar with back-to-home + ticker switcher
# ============================================================
back_l, back_mid, back_r = st.columns([1, 4, 1.4])
with back_l:
    if st.button("← Back to home", key="back_to_home", type="secondary",
                 use_container_width=True):
        st.session_state.pop("eq_active_ticker", None)
        st.rerun()
with back_mid:
    st.markdown(
        '<div class="eq-section-label" style="text-align:center; '
        'padding-top:6px;">EQUITY ANALYSIS</div>',
        unsafe_allow_html=True,
    )
with back_r:
    in_wl = is_in_watchlist(active_ticker)
    btn_label = "★ In watchlist" if in_wl else "☆ Add to watchlist"
    if st.button(btn_label, key="watchlist_toggle", type="secondary",
                 use_container_width=True):
        if in_wl:
            remove_from_watchlist(active_ticker)
        else:
            add_to_watchlist(active_ticker)
        st.rerun()

# Compact secondary inputs row — lets the user switch ticker without
# returning to the landing.
_LABELS: list[str] = ticker_labels(SP500_TOP)
ic1, ic2, ic3, ic4 = st.columns([0.9, 4.0, 2.0, 1.1])
with ic1:
    use_custom = st.toggle(
        "Custom", value=False,
        help="Toggle on to type any ticker outside the curated S&P 500 list.",
    )
with ic2:
    if use_custom:
        ticker = st.text_input(
            "Ticker", value=active_ticker, label_visibility="collapsed",
            placeholder="Type a ticker",
        ).strip().upper()
    else:
        default_idx = next(
            (i for i, lbl in enumerate(_LABELS)
             if lbl.startswith(f"{active_ticker} ")),
            0,
        )
        chosen_label = st.selectbox(
            "Ticker", options=_LABELS, index=default_idx,
            label_visibility="collapsed",
            placeholder="🔎  Search ticker…",
        )
        ticker = ticker_from_label(chosen_label)
with ic3:
    peers_raw = st.text_input(
        "Peers", value="MSFT,GOOGL,META",
        label_visibility="collapsed",
        placeholder="Comma-separated peers",
    )
with ic4:
    if st.button("Re-analyze", type="primary", use_container_width=True):
        _set_active(ticker)
        st.rerun()

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
# Compute base assumptions + restore any user overrides BEFORE
# we render the header (so the rating shown matches what the panel
# at the bottom currently holds).
# ============================================================
base_assumptions: Assumptions = calculate_default_assumptions(
    income=inc, balance=bal, cash=cf,
    beta_override=1.20,
    market_cap=_DEMO_MARKET_CAP.get(active_ticker),
)

# Hydrate the panel's current state — the user's previously-edited dict
# (saved in session_state by render_assumptions_panel on a prior run)
# wins over the freshly-computed base case. On the very first render
# we fall back to the base case so the header isn't empty.
user_state_key = f"assumptions_{active_ticker}_user"
if user_state_key in st.session_state:
    current_assumptions = Assumptions.from_dict(st.session_state[user_state_key])
else:
    current_assumptions = base_assumptions


# ============================================================
# Pipeline (single source of truth for everything below the header)
# ============================================================
peers_demo = _DEMO_PEERS.get(active_ticker, [])
sector = _DEMO_SECTOR.get(active_ticker)
current_price = _DEMO_PRICE.get(active_ticker)

with st.spinner("Running valuation pipeline…"):
    try:
        results = run_valuation(
            ticker=active_ticker,
            income=inc, balance=bal, cash=cf,
            assumptions=current_assumptions,
            peers=peers_demo,
            earnings_quality=eq,
            current_price=current_price,
            sector=sector,
        )
    except (ValuationError, InsufficientDataError) as exc:
        st.error(f"Valuation pipeline failed: {exc}")
        st.stop()

upside = None
if (results.aggregator and np.isfinite(results.aggregator.intrinsic_per_share)
        and current_price and current_price > 0):
    upside = (results.aggregator.intrinsic_per_share - current_price) / current_price


# ============================================================
# 2 — Big ticker header (price + intrinsic + rating)
# ============================================================
company_name = TICKER_META.get(active_ticker, {}).get("name", active_ticker)
sector_label = TICKER_META.get(active_ticker, {}).get("sector", sector or "—")

w52 = _DEMO_W52.get(active_ticker, (None, None))
render_ticker_header(
    ticker=active_ticker,
    company_name=company_name,
    sector=sector_label,
    market_cap=_DEMO_MARKET_CAP.get(active_ticker),
    current_price=current_price,
    daily_change_pct=_DEMO_DAILY_PCT.get(active_ticker),
    week52_low=w52[0], week52_high=w52[1],
    intrinsic=(results.aggregator.intrinsic_per_share
               if results.aggregator
               and np.isfinite(results.aggregator.intrinsic_per_share)
               else None),
    upside=upside,
    rating=results.rating,
    confidence=(results.aggregator.confidence
                if results.aggregator else None),
)


# ============================================================
# 2.5 — Company profile + Competitive landscape
# ============================================================
from ui.components.company_profile import render_company_profile
from ui.components.competitive_landscape import render_competitive_landscape

st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
render_company_profile(active_ticker)

st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">COMPETITIVE LANDSCAPE</div>',
    unsafe_allow_html=True,
)
render_competitive_landscape(
    target_ticker=active_ticker,
    target_income=inc, target_balance=bal,
    target_market_cap=_DEMO_MARKET_CAP.get(active_ticker),
    peers=peers_demo,
)


# ============================================================
# 3 — Quick metrics row (native st.metric — no HTML escape bug)
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

last = ratios.iloc[-1]
rev = float(last["Revenue"]) if "Revenue" in last else None
rev_growth = None
if "Revenue" in ratios.columns and len(ratios) >= 2:
    prev_rev = float(ratios["Revenue"].iloc[-2])
    if prev_rev > 0 and rev:
        rev_growth = (rev / prev_rev - 1.0) * 100.0
net_margin = float(last["Net Margin %"]) if "Net Margin %" in last else None
roic = float(last["ROIC %"]) if "ROIC %" in last else None

render_quick_metrics(
    revenue=rev,
    net_margin_pct=net_margin,
    roic_pct=roic,
    eq_flag=eq.overall_flag,
    revenue_yoy_pct=rev_growth,
)


# ============================================================
# 4 — Tabs
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

(tab_overview, tab_valuation, tab_financials, tab_ratios,
 tab_quality, tab_peers, tab_charts) = st.tabs([
    "Overview", "Valuation", "Financials", "Ratios",
    "Quality", "Peers", "Charts",
])


# ---- Overview ----
with tab_overview:
    # ---- 1. Returns row (vs S&P 500 benchmark) ----
    from data.market_data import get_ticker_history
    from ui.components.returns_table import (
        compute_returns, render_returns_row,
        render_benchmark_comparison, render_benchmark_row,
    )
    from ui.components.price_with_intrinsic_chart import (
        build_price_with_intrinsic_figure,
    )
    from ui.components.football_field import build_football_field_figure
    from ui.components.score_breakdown import render_score_breakdown_grid
    from ui.components.dupont_card import render_dupont_card
    from ui.components.peer_comparison_quick import render_peer_comparison_quick

    st.markdown(
        '<div class="eq-section-label">RETURNS</div>',
        unsafe_allow_html=True,
    )
    overview_period = st.session_state.get("overview_chart_period", "5y")
    price_history = get_ticker_history(active_ticker, period="10y")
    spx_history = get_ticker_history("^GSPC", period="10y")

    target_close = (price_history["Close"].dropna()
                    if not price_history.empty and "Close" in price_history.columns
                    else None)
    spx_close = (spx_history["Close"].dropna()
                 if not spx_history.empty and "Close" in spx_history.columns
                 else None)

    target_returns = compute_returns(target_close) if target_close is not None else {}
    spx_returns = compute_returns(spx_close) if spx_close is not None else {}
    render_returns_row(target_returns)

    if target_returns and spx_returns:
        comparisons = []
        for label in ("1Y", "3Y", "5Y"):
            comparisons.append(render_benchmark_comparison(
                target=target_returns.get(label),
                benchmark=spx_returns.get(label),
                label=f"S&P 500 ({label})",
            ))
        render_benchmark_row(comparisons)

    # ---- 2. Price chart with intrinsic overlays ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    pc_l, pc_r = st.columns([4, 1])
    with pc_l:
        st.markdown(
            '<div class="eq-section-label">PRICE · INTRINSIC OVERLAYS</div>',
            unsafe_allow_html=True,
        )
    with pc_r:
        period_label = st.radio(
            "price_period",
            options=["1Y", "3Y", "5Y", "10Y"],
            index=2, horizontal=True, label_visibility="collapsed",
            key=f"price_period_{active_ticker}",
        )
    period_key = {"1Y": "1y", "3Y": "3y", "5Y": "5y", "10Y": "10y"}[period_label]

    chart_history = get_ticker_history(active_ticker, period=period_key)
    if chart_history.empty:
        st.info("No price history available for this ticker (yfinance returned empty).")
    else:
        st.plotly_chart(
            build_price_with_intrinsic_figure(chart_history, results, height=400),
            use_container_width=True, config={"displayModeBar": False},
        )

    # ---- 3. Football field — valuation ranges ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">FOOTBALL FIELD · MODEL RANGES</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_football_field_figure(
            results,
            week52_low=w52[0] if w52 else None,
            week52_high=w52[1] if w52 else None,
            height=360,
        ),
        use_container_width=True, config={"displayModeBar": False},
    )

    # ---- 4. Score breakdown (Bloomberg-style 5-card grid) ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    composite = results.score.composite if results.score else 0.0
    st.markdown(
        f'<div class="eq-section-label">SCORE BREAKDOWN  ·  '
        f'<span style="color:var(--text-primary);">{composite:.0f}/100</span></div>',
        unsafe_allow_html=True,
    )
    render_score_breakdown_grid(results.score)

    # ---- 5. Valuation summary table (the per-model breakdown) ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">VALUATION SUMMARY</div>',
        unsafe_allow_html=True,
    )
    render_valuation_summary(results)

    # ---- 6. DuPont decomposition ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    render_dupont_card(inc, bal)

    # ---- 7. Quick peer comparison ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">QUICK PEER COMPARISON</div>',
        unsafe_allow_html=True,
    )
    if peers_demo:
        render_peer_comparison_quick(
            target_ticker=active_ticker,
            target_income=inc, target_balance=bal,
            target_market_cap=_DEMO_MARKET_CAP.get(active_ticker),
            target_enterprise_value=(
                (_DEMO_MARKET_CAP.get(active_ticker, 0)
                 + (float(bal["totalDebt"].iloc[-1]) if "totalDebt" in bal.columns else 0))
                if active_ticker in _DEMO_MARKET_CAP else None
            ),
            peers=peers_demo,
        )
        st.caption("Best metric per row in green, worst in red. See the **Peers** tab for the full multiples breakdown.")
    else:
        st.info("No peers configured for this ticker.")

    # ---- 8. Revenue / Net Income / FCF chart (kept) ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">REVENUE · NET INCOME · FREE CASH FLOW</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_revenue_figure(inc, cash=cf, height=300),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.caption(
        "Sections still pending live-data wiring: segments / geography, "
        "analyst ratings, institutional holders, news + sentiment, "
        "short interest, events timeline. They land when the FMP / "
        "EDGAR / news endpoints come online."
    )


# ---- Valuation ----
with tab_valuation:
    # Per-model cards
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
                sub_label=(f"WACC {results.dcf.wacc:.1%} · "
                           f"g₁ {results.dcf.stage1_growth:.1%} → "
                           f"g_t {results.dcf.terminal_growth:.1%}"),
            )
        else:
            render_valuation_card(model="DCF · 3-stage", intrinsic=None,
                                  sub_label=results.dcf_error or "unavailable")
    with vc2:
        cmp_res = results.comparables
        if cmp_res is not None and cmp_res.implied_per_share_median is not None:
            mults = ", ".join(cmp_res.multiples.keys())
            render_valuation_card(
                model="COMPARABLES",
                intrinsic=cmp_res.implied_per_share_median,
                current_price=current_price,
                range_low=cmp_res.implied_per_share_low,
                range_high=cmp_res.implied_per_share_high,
                sub_label=f"{cmp_res.n_peers_input} peers · {mults}",
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
                                  sub_label=results.monte_carlo_error or "n/a")
    with vc4:
        if results.ddm is not None:
            d = results.ddm
            render_valuation_card(
                model="DDM · 2-stage",
                intrinsic=d.intrinsic_value_per_share,
                current_price=current_price,
                sub_label=(f"DPS ${d.base_dividend:.2f} · "
                           f"g₁ {d.stage1_growth:.1%}"
                           + (f" · payout {d.payout_ratio:.0%}"
                              if d.payout_ratio is not None else "")),
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

    # WACC breakdown
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">WACC BREAKDOWN</div>',
        unsafe_allow_html=True,
    )
    w = results.wacc
    wacc_table = pd.DataFrame([
        {"Component": "Risk-free rate",          "Value": f"{w.risk_free_rate:.4f}"},
        {"Component": "× Beta",                  "Value": f"{w.beta_relevered:.2f}"},
        {"Component": "× Equity risk premium",   "Value": f"{w.equity_risk_premium:.4f}"},
        {"Component": "= Cost of equity (CAPM)", "Value": f"{w.cost_of_equity:.4f}"},
        {"Component": "Cost of debt (pre-tax)",  "Value": f"{w.cost_of_debt_pretax:.4f}"},
        {"Component": "× (1 − tax rate)",        "Value": f"{1.0 - w.tax_rate:.4f}"},
        {"Component": "= Cost of debt (after-tax)", "Value": f"{w.cost_of_debt_after_tax:.4f}"},
        {"Component": "Equity weight",           "Value": f"{w.weight_equity:.2%}"},
        {"Component": "Debt weight",             "Value": f"{w.weight_debt:.2%}"},
        {"Component": "WACC",                    "Value": f"{w.wacc:.4f}"},
    ])
    st.dataframe(wacc_table, hide_index=True, use_container_width=True)

    # DCF projection table + EV split
    if results.dcf is not None:
        dcf = results.dcf
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">DCF — FCF PROJECTION (USD MM)</div>',
            unsafe_allow_html=True,
        )
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

    # Sensitivity heatmap
    if results.dcf is not None:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">SENSITIVITY · INTRINSIC $/SHARE</div>',
            unsafe_allow_html=True,
        )
        wacc_grid = [round(results.wacc.wacc + d, 4)
                     for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
        g_grid = [round(current_assumptions.terminal_growth + d, 4)
                  for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
        g_override = current_assumptions.override_growth or None
        sens = sensitivity_table(
            income=inc, balance=bal, cash=cf,
            wacc_grid=wacc_grid, g_grid=g_grid,
            stage1_growth=g_override,
        )
        sens.index = [f"{w_:.2%}" for w_ in sens.index]
        sens.columns = [f"{g:.2%}" for g in sens.columns]
        sens.index.name = "WACC ↓ / g →"
        st.dataframe(sens.round(2), use_container_width=True)

    # Monte Carlo distribution
    if results.monte_carlo is not None:
        mc = results.monte_carlo
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">MONTE CARLO DISTRIBUTION</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            build_mc_distribution_figure(
                mc.intrinsic_distribution,
                percentiles=mc.percentiles,
                current_price=current_price,
            ),
            use_container_width=True, config={"displayModeBar": False},
        )


# ---- Financials ----
with tab_financials:
    # ---- Top bar: view-mode toggle + Excel download on the right ----
    fin_l, fin_r1, fin_r2 = st.columns([4, 1.4, 1.4])
    with fin_l:
        view_mode_label = st.radio(
            "view_mode_pill",
            options=["Absolute", "Common size", "Growth"],
            index=0, horizontal=True, label_visibility="collapsed",
            key=f"fin_view_{active_ticker}",
        )
    view_mode = {
        "Absolute":     "absolute",
        "Common size":  "common_size",
        "Growth":       "growth",
    }[view_mode_label]

    with fin_r2:
        try:
            from exports.excel_export import export_financials_xlsx
            xlsx_bytes = export_financials_xlsx(
                income=inc, balance=bal, cash=cf, ticker=active_ticker,
            )
            st.download_button(
                "Download Excel",
                data=xlsx_bytes,
                file_name=f"{active_ticker}_financials.xlsx",
                mime=("application/vnd.openxmlformats-officedocument."
                      "spreadsheetml.sheet"),
                use_container_width=True,
                key=f"xlsx_{active_ticker}",
            )
        except ImportError:
            st.caption("openpyxl not installed — Excel export unavailable.")

    # ---- Income Statement ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'INCOME STATEMENT</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_income_chart(inc, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_income_statement(inc, view=view_mode)

    # ---- Balance Sheet ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'BALANCE SHEET</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_balance_chart(bal, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_balance_sheet(bal, view=view_mode)

    # ---- Cash Flow ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'CASH FLOW STATEMENT</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_fcf_chart(cf, income=inc, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_cash_flow(cf, view=view_mode)

    # ---- Financial Ratios (kept as st.dataframe — already legible) ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'FINANCIAL RATIOS</div>',
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


# ---- Ratios ----
with tab_ratios:
    from ui.components.ratios_grid import render_ratios_grid
    market_cap = _DEMO_MARKET_CAP.get(active_ticker)
    enterprise_value = None
    if market_cap is not None and "totalDebt" in bal.columns:
        try:
            enterprise_value = market_cap + float(bal["totalDebt"].iloc[-1])
        except Exception:
            enterprise_value = None
    render_ratios_grid(
        income=inc, balance=bal, cash=cf,
        ratios=ratios,
        sector=sector_label,
        current_price=current_price,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
    )


# ---- Quality ----
with tab_quality:
    st.markdown(
        '<div class="eq-section-label">EARNINGS QUALITY · OVERALL FLAG '
        f'<span style="color:var(--accent);">{eq.overall_flag.upper()}</span>'
        '</div>',
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
    else:
        st.info("Earnings-quality models could not be computed for this fixture.")


# ---- Peers ----
with tab_peers:
    if results.comparables is not None and results.comparables.multiples:
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

        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">PEER ROSTER</div>',
            unsafe_allow_html=True,
        )
        roster = pd.DataFrame([{
            "Ticker":      p.ticker,
            "Market cap":  p.market_cap,
            "Revenue":     p.revenue,
            "EBITDA":      p.ebitda,
            "Net income":  p.net_income,
        } for p in peers_demo])
        st.dataframe(
            roster, hide_index=True, use_container_width=True,
            column_config={
                "Market cap": st.column_config.NumberColumn(format="$%,.0f"),
                "Revenue":    st.column_config.NumberColumn(format="$%,.0f"),
                "EBITDA":     st.column_config.NumberColumn(format="$%,.0f"),
                "Net income": st.column_config.NumberColumn(format="$%,.0f"),
            },
        )
    else:
        st.info(results.comparables_error
                or "No comparable peers configured for this ticker.")


# ---- Charts ----
with tab_charts:
    st.markdown(
        '<div class="eq-section-label">REVENUE · NET INCOME · FREE CASH FLOW</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_revenue_figure(inc, cash=cf, height=320),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">MARGIN EVOLUTION</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_margins_figure(inc, bal, cf, height=320),
        use_container_width=True, config={"displayModeBar": False},
    )


# ============================================================
# 5 — Assumptions panel (BOTTOM, collapsed by default)
# ============================================================
st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">ANALYSIS INPUTS</div>',
    unsafe_allow_html=True,
)

# Offer to load saved custom assumptions on the first visit per session
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
            st.session_state[user_state_key] = saved_params
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

# Note: editing here triggers a Streamlit rerun → the pipeline at the top
# re-executes with the new assumptions and the entire page above updates.
_ = render_assumptions_panel(
    ticker=active_ticker,
    base=base_assumptions,
    expanded=False,                    # collapsed at the bottom by default
    on_save=lambda a: save_assumptions(active_ticker, a.to_dict()),
    on_reset=lambda: delete_assumptions(active_ticker),
)

if base_assumptions.warnings:
    with st.expander("ℹ Default-derivation notes", expanded=False):
        for warn in base_assumptions.warnings:
            st.markdown(f"- {warn}")


# ============================================================
# 6 — Footer
# ============================================================
st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
st.caption(
    "Demo data: AAPL / MSFT / JPM via local fixtures. Live prices and "
    "FMP fundamentals will replace the hard-coded values when the live "
    "provider is wired in. Save assumptions per-ticker via the panel above. "
    "This is not investment advice."
)
