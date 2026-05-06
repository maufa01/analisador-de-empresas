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
from typing import Optional

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
# LIVE-ONLY data path. Every figure on the page comes from a real
# provider. The previous _DEMO_* dicts (AAPL=$185, hardcoded 52w
# range $164–$198, etc.) have been deleted — they were the source of
# the stale-price bug.
#
# Data flow per ticker:
#     1. validate_ticker(ticker)         — confirm the ticker exists.
#     2. get_company_info(ticker)        — sector, market cap, 52w, etc.
#     3. get_current_price(ticker)       — live quote (Finnhub → yfinance).
#     4. require_financials(ticker)      — SEC EDGAR → yfinance → FMP.
#     5. fetch_live_peers(ticker, sector) — peer roster from FMP if available.
#
# Fixtures (tests/fixtures/*.py) still ship with the repo for pytest;
# they are never read by the page.
# ============================================================
from analysis.data_adapter import (
    DataSourceError,
    get_current_price as _live_get_current_price,
    get_company_info as _live_get_company_info,
    require_financials as _live_require_financials,
)


def _fetch_live_peers(ticker: str, sector: Optional[str]) -> list[PeerSnapshot]:
    """Best-effort peer roster from FMP. Returns [] when no key / no peers."""
    try:
        from data.fmp_provider import FMPProvider
        from core.exceptions import MissingAPIKeyError, ProviderError
    except Exception:
        return []
    try:
        prov = FMPProvider()
    except MissingAPIKeyError:
        return []
    except Exception:
        return []
    try:
        peers = prov.fetch_peers(ticker) or []
    except (MissingAPIKeyError, ProviderError):
        return []
    except Exception:
        return []
    out: list[PeerSnapshot] = []
    for p in peers[:6]:
        # FMP fetch_peers returns dicts with at least 'symbol' and basic stats
        if isinstance(p, str):
            out.append(PeerSnapshot(p))
            continue
        if not isinstance(p, dict):
            continue
        sym = p.get("symbol") or p.get("ticker")
        if not sym:
            continue
        out.append(PeerSnapshot(
            ticker=sym,
            market_cap=p.get("marketCap") or p.get("mktCap"),
            enterprise_value=p.get("enterpriseValue"),
            net_income=p.get("netIncomeTTM") or p.get("netIncome"),
            revenue=p.get("revenueTTM") or p.get("revenue"),
            ebitda=p.get("ebitdaTTM") or p.get("ebitda"),
            book_value=p.get("totalEquity") or p.get("bookValue"),
        ))
    return out


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
# returning to the landing. (The old comma-separated peers field has
# been removed; peer comparison now lives in the Overview tab as the
# Price Comparison panel — search, add, remove, time range, normalised
# vs absolute, performance summary.)
_LABELS: list[str] = ticker_labels(SP500_TOP)
ic1, ic2, ic3 = st.columns([0.9, 5.5, 1.4])
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
    if st.button("Re-analyze", type="primary", use_container_width=True):
        _set_active(ticker)
        st.rerun()

# ============================================================
# Universal resolver — classify the ticker and route accordingly.
# Sector dashboards (bank / REIT / insurance) render above the
# standard pipeline; ETFs / crypto / indices / errors short-circuit
# and replace the standard analysis entirely.
# ============================================================
from analysis.universal_resolver import resolve as _resolve_ticker
from ui.components.resolver_views import maybe_render_non_standard_view

_resolved = _resolve_ticker(active_ticker)
if maybe_render_non_standard_view(_resolved):
    st.stop()

# The resolver already validated the ticker against SEC EDGAR and / or
# yfinance during classification. We trust that result — re-running
# validate_ticker here would just hit two more providers and add a
# fragile failure mode (race vs. yfinance / Finnhub rate limits).
# If a downstream fetch (price, company info, financials) flakes,
# its own try/except below produces a specific, accurate error.

with st.spinner(f"Fetching {active_ticker} live data…"):
    try:
        live_info = _live_get_company_info(active_ticker)
    except DataSourceError as exc:
        st.error(f"❌ Could not fetch company info for {active_ticker}.")
        st.caption(f"Providers tried: {', '.join(exc.providers_tried)}")
        st.stop()

    try:
        live_quote = _live_get_current_price(active_ticker)
    except DataSourceError as exc:
        st.error(f"❌ Could not fetch a current price for {active_ticker}.")
        st.caption(f"Providers tried: {', '.join(exc.providers_tried)}")
        st.stop()

    try:
        bundle = _live_require_financials(active_ticker)
    except DataSourceError as exc:
        st.error(
            f"❌ Could not fetch financial statements for {active_ticker} "
            f"from any provider."
        )
        st.caption(
            f"Providers tried: {', '.join(exc.providers_tried)}. "
            "SEC EDGAR is the most reliable — make sure SEC_USER_AGENT is set."
        )
        st.stop()

inc, bal, cf = bundle.income, bundle.balance, bundle.cash
ratios = calculate_ratios(inc, bal, cf)
eq = assess_earnings_quality(inc, bal, cf)

# Single source of truth for everything the page needs from "info"
sector = live_info.get("sector") or live_info.get("industry")
current_price = float(live_quote["price"])
market_cap_live = live_info.get("market_cap")
w52_low = live_info.get("fifty_two_week_low")
w52_high = live_info.get("fifty_two_week_high")
daily_change_pct = float(live_quote.get("change_pct") or 0.0)
peers_demo = _fetch_live_peers(active_ticker, sector)


# ============================================================
# Compute base assumptions + restore any user overrides BEFORE
# we render the header (so the rating shown matches what the panel
# at the bottom currently holds).
# ============================================================
base_assumptions: Assumptions = calculate_default_assumptions(
    income=inc, balance=bal, cash=cf,
    beta_override=(live_info.get("beta") or 1.20),
    market_cap=market_cap_live,
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
# Pipeline (single source of truth for everything below the header).
# All inputs (sector, current_price, peers_demo) were resolved live
# above — there are no demo fallbacks.
# ============================================================
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

# Persist score/rating into watchlist meta so the alert checker can detect
# score changes the next time it runs.
if is_in_watchlist(active_ticker):
    try:
        from data.watchlist_alerts_db import update_last_check
        update_last_check(
            active_ticker,
            score=int(round(results.score.composite)) if results.score else None,
            rating=(results.rating.verdict if results.rating else None),
        )
    except Exception:
        pass


# ============================================================
# 2 — Big ticker header (price + intrinsic + rating)
# ============================================================
# Live company name; fall back to the static curated name if yfinance/Finnhub
# didn't supply one (rare).
company_name = (live_info.get("name")
                or TICKER_META.get(active_ticker, {}).get("name", active_ticker))
sector_label = (live_info.get("sector")
                or live_info.get("industry")
                or TICKER_META.get(active_ticker, {}).get("sector")
                or "—")

render_ticker_header(
    ticker=active_ticker,
    company_name=company_name,
    sector=sector_label,
    market_cap=market_cap_live,
    current_price=current_price,
    daily_change_pct=daily_change_pct,
    week52_low=w52_low, week52_high=w52_high,
    intrinsic=(results.aggregator.intrinsic_per_share
               if results.aggregator
               and np.isfinite(results.aggregator.intrinsic_per_share)
               else None),
    upside=upside,
    rating=results.rating,
    confidence=(results.aggregator.confidence
                if results.aggregator else None),
)

# ---- Data-provenance strip — make it impossible to confuse fixture
#      data with live data again. Shows which provider fed each major
#      block plus how fresh the price quote is.
from ui.components.data_source_badge import source_chip
_price_chip = source_chip(
    live_quote.get("source", "—"),
    fetched_at=live_quote.get("fetched_at"),
    is_realtime=bool(live_quote.get("is_realtime")),
)
_info_chip = source_chip(live_info.get("source", "—"))
_fin_chip = source_chip(bundle.source if bundle else "—")
st.markdown(
    '<div style="display:flex; gap:18px; flex-wrap:wrap; '
    'margin:6px 0 14px 0; padding:8px 14px; background:var(--surface); '
    'border:1px solid var(--border); border-radius:6px;">'
    f'<span style="color:var(--text-muted); font-size:10px; '
    f'letter-spacing:0.5px;">PRICE {_price_chip}</span>'
    f'<span style="color:var(--text-muted); font-size:10px; '
    f'letter-spacing:0.5px;">COMPANY INFO {_info_chip}</span>'
    f'<span style="color:var(--text-muted); font-size:10px; '
    f'letter-spacing:0.5px;">FINANCIALS {_fin_chip}</span>'
    '</div>',
    unsafe_allow_html=True,
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
    target_market_cap=market_cap_live,
    peers=peers_demo,
)


# ============================================================
# 3 — Quick metrics row (native st.metric — no HTML escape bug)
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

def _safe_float(v):
    """Return float(v) when present and finite; None otherwise.
    Critical: float(NaN) returns NaN (not None), and NaN propagates
    through the UI as '$nan' / 'nan%'. Catch every empty / non-finite
    case here so the cards render '—' instead of 'nan'."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f) or not np.isfinite(f):
        return None
    return f


def _safe_metric(row, key):
    """Pull row[key] and pass through _safe_float."""
    if key not in row:
        return None
    return _safe_float(row[key])


last = ratios.iloc[-1]
rev = _safe_metric(last, "Revenue")
prev_rev = (_safe_float(ratios["Revenue"].iloc[-2])
            if "Revenue" in ratios.columns and len(ratios) >= 2 else None)
rev_growth = None
if rev is not None and prev_rev and prev_rev > 0:
    rev_growth = (rev / prev_rev - 1.0) * 100.0
net_margin = _safe_metric(last, "Net Margin %")
roic = _safe_metric(last, "ROIC %")

render_quick_metrics(
    revenue=rev,
    net_margin_pct=net_margin,
    roic_pct=roic,
    eq_flag=eq.overall_flag,
    revenue_yoy_pct=rev_growth,
)


# ============================================================
# 3.5 — Peer-relative ranking
# ============================================================
from analysis.peer_ranking import compute_peer_rankings
from ui.components.peer_ranking_table import render_peer_ranking

st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
if peers_demo:
    market_cap_pr = market_cap_live
    enterprise_value_pr = None
    if market_cap_pr is not None and "totalDebt" in bal.columns:
        try:
            enterprise_value_pr = market_cap_pr + float(bal["totalDebt"].iloc[-1])
        except Exception:
            enterprise_value_pr = None
    ranking = compute_peer_rankings(
        target_ticker=active_ticker,
        target_income=inc, target_balance=bal, target_cash=cf,
        target_market_cap=market_cap_pr,
        target_enterprise_value=enterprise_value_pr,
        peers=peers_demo,
    )
    render_peer_ranking(ranking)


# ============================================================
# 4 — Tabs
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

(tab_overview, tab_valuation, tab_financials, tab_ratios,
 tab_quality, tab_peers, tab_capital, tab_insiders,
 tab_charts) = st.tabs([
    "Overview", "Valuation", "Financials", "Ratios",
    "Quality", "Peers", "Capital allocation", "Insiders",
    "Charts",
])


# ---- Overview ----
with tab_overview:
    # ---- Next earnings card (Finnhub, only if ≤60 days away) ----
    from ui.components.next_earnings_card import render_next_earnings_card
    render_next_earnings_card(active_ticker, horizon_days=60)

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
            week52_low=w52_low,
            week52_high=w52_high,
            height=360,
        ),
        use_container_width=True, config={"displayModeBar": False},
    )

    # ---- 3.5  Price comparison (replaces the old peers field) ----
    from ui.components.price_comparison import render_price_comparison
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    render_price_comparison(active_ticker)

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
            target_market_cap=market_cap_live,
            target_enterprise_value=(
                ((market_cap_live or 0)
                 + (float(bal["totalDebt"].iloc[-1]) if "totalDebt" in bal.columns else 0))
                if market_cap_live is not None else None
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

    # ---- Institutional holders snapshot (yfinance) ----
    from analysis.institutional_analysis import get_holdings_snapshot
    from ui.components.institutional_holders_card import render_institutional_holders_card

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">INSTITUTIONAL HOLDERS · SNAPSHOT</div>',
        unsafe_allow_html=True,
    )
    snap = get_holdings_snapshot(active_ticker)
    render_institutional_holders_card(snap, target_ticker=active_ticker)

    # ---- Dividend safety ----
    from analysis.dividend_safety import analyze_dividend_safety
    from ui.components.dividend_safety_card import render_dividend_safety_card

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    div_res = analyze_dividend_safety(income=inc, balance=bal, cash=cf)
    render_dividend_safety_card(div_res)

    # ---- News & Sentiment — Marketaux articles + Finnhub insider/analyst ----
    from ui.components.news_combined_section import render_news_combined_section

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    render_news_combined_section(active_ticker)

    # ---- Legacy yfinance + VADER fallback ----
    # Keeps working when no Marketaux key — cheap headline-only sentiment.
    with st.expander("Headline-only sentiment (yfinance + VADER fallback)",
                     expanded=False):
        from analysis.news_sentiment import analyze_ticker_news
        from ui.components.news_sentiment_panel import render_news_sentiment_panel
        engine_label = st.radio(
            "sentiment_engine",
            options=["VADER (fast)", "FinBERT (heavy, finance-tuned)"],
            index=0, horizontal=True, label_visibility="collapsed",
            key=f"sent_engine_{active_ticker}",
        )
        engine = "finbert" if engine_label.startswith("FinBERT") else "vader"
        news_res = analyze_ticker_news(active_ticker, limit=30, engine=engine)
        render_news_sentiment_panel(news_res)

    # ---- Segments + Geography (FMP-only) ----
    from analysis.segments import (
        analyze_segments, analyze_geography, value_segments_sotp,
    )
    from ui.components.segments_panel import (
        render_segments_panel, render_geography_panel, render_sotp_panel,
    )

    segments_res = analyze_segments(active_ticker)
    geography_res = analyze_geography(active_ticker)

    if segments_res.available or geography_res.available:
        st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
        if segments_res.available:
            render_segments_panel(segments_res)
        if geography_res.available:
            st.markdown("<div style='height:14px;'></div>",
                        unsafe_allow_html=True)
            render_geography_panel(geography_res)

        # SOTP only makes sense with at least 2 segments
        if segments_res.available and segments_res.n_segments >= 2:
            st.markdown("<div style='height:14px;'></div>",
                        unsafe_allow_html=True)
            try:
                from analysis.ratios import _get
                shares_out = None
                _shares = _get(inc, "weighted_avg_shares")
                if _shares is not None and not _shares.dropna().empty:
                    shares_out = float(_shares.dropna().iloc[-1])
                _cash = _get(bal, "cash_eq")
                _debt = _get(bal, "total_debt")
                cash_bs = float(_cash.dropna().iloc[-1]) if _cash is not None and not _cash.dropna().empty else 0.0
                debt_bs = float(_debt.dropna().iloc[-1]) if _debt is not None and not _debt.dropna().empty else 0.0
                sotp_res = value_segments_sotp(
                    segments=segments_res,
                    market_cap=market_cap_live,
                    net_debt=(debt_bs - cash_bs),
                    shares_outstanding=shares_out,
                    current_price=current_price,
                )
                render_sotp_panel(sotp_res)
            except Exception:
                pass

    # ---- AI thesis prompt generator (offline mode) ----
    from analysis.shareholder_yield import calculate_shareholder_yield as _sy_for_prompt
    from analysis.ai_thesis_prompt import build_thesis_prompt
    from ui.components.ai_thesis_panel import render_ai_thesis_panel

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    if st.toggle("AI investment thesis (offline copy-paste)",
                 value=False, key=f"ai_thesis_toggle_{active_ticker}"):
        _sy_for_thesis = _sy_for_prompt(
            cash=cf, market_cap=market_cap_live,
        )
        thesis_prompt = build_thesis_prompt(
            ticker=active_ticker,
            company_name=company_name,
            sector=sector_label,
            industry=TICKER_META.get(active_ticker, {}).get("industry"),
            market_cap=market_cap_live,
            current_price=current_price,
            valuation_results=results,
            earnings_quality=eq,
            dividend_safety=div_res,
            shareholder_yield=_sy_for_thesis,
            news_sentiment=news_res,
        )
        render_ai_thesis_panel(thesis_prompt, ticker=active_ticker)

    st.caption(
        "Pending live-data wiring: segments / geography, analyst ratings, "
        "short interest, events timeline. They land when the FMP / EDGAR "
        "endpoints come online."
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

    # Wall Street consensus (Finnhub) — recommendation distribution +
    # price target with divergence vs the aggregator.
    from ui.components.analyst_consensus_panel import render_analyst_consensus_panel
    aggregator_intr = (results.aggregator.intrinsic_per_share
                        if results.aggregator and np.isfinite(
                            results.aggregator.intrinsic_per_share
                        ) else None)
    render_analyst_consensus_panel(
        active_ticker,
        aggregator_intrinsic=aggregator_intr,
        current_price=current_price,
    )

    # Reverse DCF — what growth justifies the current price?
    if current_price and current_price > 0 and results.dcf is not None:
        from valuation.reverse_dcf import run_reverse_dcf
        from ui.components.reverse_dcf_section import render_reverse_dcf_section
        from analysis.damodaran_loader import get_industry_benchmarks

        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">REVERSE DCF · MARKET-IMPLIED GROWTH</div>',
            unsafe_allow_html=True,
        )
        bench = get_industry_benchmarks(
            (TICKER_META.get(active_ticker, {}) or {}).get("sector"),
            sector=sector,
        )
        industry_growth = (bench.get("growth") / 100.0
                           if bench.get("growth") is not None else None)
        rev_result = run_reverse_dcf(
            income=inc, balance=bal, cash=cf,
            target_price=float(current_price),
            wacc=results.wacc.wacc,
            terminal_growth=current_assumptions.terminal_growth,
            stage1_years=current_assumptions.stage1_years,
            stage2_years=current_assumptions.stage2_years,
            industry_growth=industry_growth,
        )
        render_reverse_dcf_section(rev_result)

    # Sensitivity heatmap (now Plotly with current-scenario star)
    if results.dcf is not None:
        from ui.charts.sensitivity_heatmap import build_sensitivity_heatmap
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
        st.plotly_chart(
            build_sensitivity_heatmap(
                sens,
                current_price=current_price,
                current_wacc=results.wacc.wacc,
                current_g=current_assumptions.terminal_growth,
                height=380,
            ),
            use_container_width=True, config={"displayModeBar": False},
        )

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

    # ---- Earnings track record (beats / misses via yfinance) ----
    from analysis.earnings_track_record import get_earnings_history
    from ui.components.earnings_history_chart import render_earnings_track_record

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">EARNINGS TRACK RECORD · BEATS vs MISSES</div>',
        unsafe_allow_html=True,
    )
    eh = get_earnings_history(active_ticker)
    render_earnings_track_record(eh)

    # ---- Stress testing (rates / USD / recession / sector) ----
    from analysis.stress_testing import (
        stress_test_rates, stress_test_usd,
        stress_test_recession, stress_test_sector,
    )
    from ui.components.stress_test_panel import render_stress_test_panel

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    rates_res = stress_test_rates(
        income=inc, balance=bal, cash=cf,
        assumptions=current_assumptions, current_price=current_price,
    )
    usd_res = stress_test_usd(
        income=inc, balance=bal, cash=cf,
        assumptions=current_assumptions, sector=sector_label,
    )
    recession_res = stress_test_recession(
        income=inc, balance=bal, cash=cf,
        assumptions=current_assumptions,
    )
    sector_res = stress_test_sector(
        income=inc, balance=bal, cash=cf,
        assumptions=current_assumptions, sector=sector_label,
    )
    render_stress_test_panel(
        rates=rates_res, usd=usd_res,
        recession=recession_res, sector=sector_res,
    )


# ---- Financials ----
with tab_financials:
    # ---- SEC EDGAR statements viewer (primary view) ----
    from ui.components.financial_statements_panel import (
        render_financial_statements_panel,
    )
    render_financial_statements_panel(active_ticker)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">ALTERNATIVE VIEW · YFINANCE / FMP</div>',
        unsafe_allow_html=True,
    )

    # ---- Legacy view (yfinance / FMP camelCase) ----
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

    # Drop duplicate period_end rows (SEC sometimes ships restatements /
    # 10-K/A amendments under the same fiscal-year-end). Keep the most
    # recent one — ratios is sorted ascending by date, so 'last' wins.
    ratios_dedup = ratios[~ratios.index.duplicated(keep="last")]
    transposed = ratios_dedup[show_cols].T

    # Year-only labels collide when two filings sit in the same year
    # (e.g. fiscal-year-end shifts). Disambiguate with a numeric suffix
    # so st.dataframe / Arrow doesn't raise 'Duplicate column names'.
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for d in transposed.columns:
        base = d.strftime("%Y") if hasattr(d, "strftime") else str(d)
        n = seen.get(base, 0)
        seen[base] = n + 1
        new_cols.append(base if n == 0 else f"{base} ({n + 1})")
    transposed.columns = new_cols
    st.dataframe(transposed.round(2), use_container_width=True, height=440)


# ---- Ratios ----
with tab_ratios:
    # ---- SEC-driven Ratio Engine (primary view, US-listed tickers) ----
    from ui.components.ratios_engine_panel import render_ratios_engine_panel
    render_ratios_engine_panel(
        active_ticker,
        market_cap=market_cap_live,
        current_price=current_price,
        sector=sector_label,
    )

    # ---- Legacy yfinance-driven ratios grid (fallback for non-US) ----
    with st.expander("Alternative ratios — yfinance source", expanded=False):
        from ui.components.ratios_grid import render_ratios_grid
        market_cap = market_cap_live
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
    from ui.components.eq_score_card import render_earnings_quality_detail
    from ui.components.red_flags_comparison import render_red_flags_comparison

    if any(f is not None for f in (eq.beneish, eq.piotroski, eq.sloan)):
        render_earnings_quality_detail(eq)
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        render_red_flags_comparison(active_ticker, eq)
    else:
        st.info("Earnings-quality models could not be computed for this fixture.")

    # ---- Balance-sheet forensics ----
    from analysis.balance_sheet_quality import analyze_balance_sheet_quality
    from ui.components.balance_sheet_forensics_card import render_balance_sheet_forensics

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    bs_res = analyze_balance_sheet_quality(income=inc, balance=bal)
    render_balance_sheet_forensics(bs_res)

    # ---- Revenue quality ----
    from analysis.revenue_quality import analyze_revenue_quality
    from ui.components.revenue_quality_card import render_revenue_quality_card

    industry_label = TICKER_META.get(active_ticker, {}).get("industry")
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    rev_q = analyze_revenue_quality(
        income=inc, sector=sector_label, industry=industry_label,
    )
    render_revenue_quality_card(rev_q)

    # ---- Earnings volatility (compounder vs cyclical) ----
    from analysis.earnings_volatility import analyze_earnings_volatility
    from ui.components.earnings_volatility_card import render_earnings_volatility_card

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    ev = analyze_earnings_volatility(income=inc)
    render_earnings_volatility_card(ev)

    # ---- ESG scores (Finnhub) — last so it's optional in the visual hierarchy ----
    from ui.components.esg_panel import render_esg_panel
    render_esg_panel(active_ticker)


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


# ---- Capital allocation ----
with tab_capital:
    from analysis.capital_allocation import analyze_capital_allocation
    from analysis.working_capital import analyze_ccc
    from ui.components.capital_allocation_dashboard import (
        render_capital_allocation_dashboard,
    )
    from ui.components.ccc_chart import render_ccc_dashboard

    capital_result = analyze_capital_allocation(
        income=inc, balance=bal, cash=cf,
        market_cap=market_cap_live,
    )
    render_capital_allocation_dashboard(capital_result)

    # ---- Cash Conversion Cycle ----
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">WORKING CAPITAL · CASH CONVERSION CYCLE</div>',
        unsafe_allow_html=True,
    )
    ccc_result = analyze_ccc(income=inc, balance=bal, sector=sector)
    render_ccc_dashboard(ccc_result)

    # ---- Shareholder yield ----
    from analysis.shareholder_yield import calculate_shareholder_yield
    from ui.components.shareholder_yield_card import render_shareholder_yield_card

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    sy_result = calculate_shareholder_yield(
        cash=cf, market_cap=market_cap_live,
    )
    render_shareholder_yield_card(sy_result)


# ---- Insiders (real Form-4 analysis when FMP key configured) ----
with tab_insiders:
    from analysis.insider_analysis import analyze_insider_activity
    from analysis.etf_analysis import analyze_etf_holdings
    from ui.components.insider_panel import render_insider_panel
    from ui.components.etf_holdings_panel import render_etf_holdings_panel
    from ui.components.sec_insiders_panel import render_sec_insiders_panel
    from ui.components.senate_trading_panel import render_senate_trading_panel

    sub_corp, sub_gov = st.tabs([
        "Corporate insiders (Form 4)", "Government trades",
    ])

    with sub_corp:
        # ---- SEC EDGAR Form 4 (free, no key needed) ----
        render_sec_insiders_panel(active_ticker)

        st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

        # ---- FMP-aggregated Form 4 (when key is configured) ----
        insider_res = analyze_insider_activity(active_ticker, months=24)
        render_insider_panel(insider_res)

        st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
        etf_res = analyze_etf_holdings(active_ticker)
        render_etf_holdings_panel(etf_res)

    with sub_gov:
        render_senate_trading_panel(active_ticker)


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
