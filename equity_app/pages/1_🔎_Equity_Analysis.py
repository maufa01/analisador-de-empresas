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
from analysis.quality import assess_earnings_quality
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


# Centralised cap so income / balance / cashflow / ratios all show the
# same window. SEC EDGAR ships 30+ years of history with multiple filings
# per fiscal year (10-K + 10-K/A); without dedup the table renders with
# 4 columns labelled "FY 2008".
_FINANCIALS_YEARS = 5

def _dedup_and_cap_years(df: pd.DataFrame, years: int = _FINANCIALS_YEARS) -> pd.DataFrame:
    """Sort ascending, keep latest filing per fiscal year, return last N years."""
    if df is None or df.empty or years <= 0:
        return df
    idx = pd.to_datetime(df.index, errors="coerce")
    if idx.isna().all():
        return df.tail(years)
    df = df.copy()
    df.index = idx
    df = df.sort_index()
    keep_mask = ~pd.Series(df.index.year, index=df.index).duplicated(keep="last").values
    df = df.iloc[keep_mask]
    return df.tail(years)
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


# Legacy ``_fetch_live_peers`` (FMP-only, no fallback) was removed in
# P10.8 — it was already shadowed by ``data.peer_resolver.fetch_live_peers``
# (cascading FMP → S&P-500 META → SECTOR_DEFAULT_PEERS) which is what
# load_bundle() actually calls. Keeping the legacy function around just
# pulled in a useless ``MissingAPIKeyError`` warning chain on every page
# load when no FMP key is set.


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

# Macro context strip — one thin row of 10Y / Fed funds / CPI / unemp
# (P11.A1 replacement for the full Macro page). Cached 1h, silent no-op
# without FRED_API_KEY.
from ui.components.macro_context_strip import render_macro_strip
render_macro_strip()

# Compact secondary inputs row — lets the user switch ticker without
# returning to the landing. (The old comma-separated peers field has
# been removed; peer comparison now lives in the Overview tab as the
# Price Comparison panel — search, add, remove, time range, normalised
# vs absolute, performance summary.)
# Pre-filter the dropdown to operating companies (P12.B3) — utilities,
# REITs, banks, insurers, BDCs, MLPs, ETFs are still analysable via the
# direct text input (with the soft-block warning), but they don't
# clutter the SP500_TOP picklist.
from analysis.security_classifier import is_operating_company
from analysis.etf_detector import is_fund_quick
from analysis.reit_detector import is_reit_quick
from analysis.bank_detector import is_bank_quick
from data.constituents import META as _TICKER_META


def _is_excluded_from_dropdown(sym: str, name: str) -> bool:
    """Belt-and-suspenders filter — security_classifier already excludes
    most non-operating tickers, but the explicit single-purpose detectors
    (P13/P14) cover edge cases where industry strings are missing."""
    if is_fund_quick(sym) or is_reit_quick(sym) or is_bank_quick(sym):
        return True
    return not is_operating_company(
        sym,
        sector=_TICKER_META.get(sym, {}).get("sector"),
        industry=_TICKER_META.get(sym, {}).get("industry"),
        name=name,
    )


_OPERATING_SP500: dict[str, str] = {
    sym: name for sym, name in SP500_TOP.items()
    if not _is_excluded_from_dropdown(sym, name)
}
_LABELS: list[str] = ticker_labels(_OPERATING_SP500)
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

# ---- Parallel hydration via load_bundle (4 fetches in parallel + ----
# ---- peers + income healing, cached 10 min per ticker) -------------
from analysis.parallel_loader import load_bundle

with st.spinner(f"Fetching {active_ticker} live data…"):
    bundle = load_bundle(active_ticker)

# Friendly errors for the most common failure modes — render structured
# per-provider details when DataSourceError carries .attempts.
from ui.components.provider_error_panel import render_provider_error_panel

def _bundle_attempts(name: str):
    exc = bundle.exceptions.get(name)
    return getattr(exc, "attempts", None) if exc is not None else None

if not bundle.quote and "quote" in bundle.errors:
    render_provider_error_panel(
        title=f"Could not fetch a current price for {active_ticker}.",
        message=str(bundle.exceptions.get("quote")
                    or bundle.errors.get("quote", "")),
        attempts=_bundle_attempts("quote"),
    )
    st.stop()
if not bundle.info and "info" in bundle.errors:
    render_provider_error_panel(
        title=f"Could not fetch company info for {active_ticker}.",
        message=str(bundle.exceptions.get("info")
                    or bundle.errors.get("info", "")),
        attempts=_bundle_attempts("info"),
    )
    st.stop()
if bundle.income.empty:
    err_reason = bundle.errors.get("financials", "no provider returned data")
    st.error(
        f"❌ Could not fetch financial statements for {active_ticker} "
        f"from any provider."
    )
    st.caption(
        f"Reason: {err_reason}. SEC EDGAR is the most reliable — make "
        "sure SEC_USER_AGENT is set."
    )
    st.stop()

# Aliases the rest of the page already uses — keep so we don't have to
# rewrite every component below.
live_info = bundle.info
live_quote = bundle.quote
inc, bal, cf = bundle.income, bundle.balance, bundle.cash
ratios = calculate_ratios(inc, bal, cf)
eq = assess_earnings_quality(inc, bal, cf)

sector = bundle.sector or live_info.get("industry")
current_price = float(live_quote.get("price") or 0.0)
market_cap_live = bundle.market_cap
w52_low = live_info.get("fifty_two_week_low")
w52_high = live_info.get("fifty_two_week_high")
daily_change_pct = float(live_quote.get("change_pct") or 0.0)
peers_demo = bundle.peers


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
# Hard blocks (P13 / P14) — fund / REIT / bank get a definitive stop
# with a sector-specific explanation BEFORE the broader soft-block. No
# override here: these three categories have well-known alternative
# valuation models that would mislead the user if we let them through.
# ============================================================
from analysis.etf_detector import detect_fund
from analysis.reit_detector import detect_reit
from analysis.bank_detector import detect_bank


def _ref_metric_row(metrics: list[tuple[str, str]]) -> None:
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, value)


# ---- ETF / fund ----
_fund_check = detect_fund(active_ticker, bundle.fmp_profile, live_info)
if _fund_check.is_fund:
    st.error(
        f"🚫 **{active_ticker}** is a fund / ETF.\n\n"
        f"This app analyses **operating companies**, not investment "
        f"vehicles. Valuation models (DCF, comparables, Monte Carlo) do "
        f"not apply to funds — their value is the sum of the holdings' "
        f"NAV, not generated FCF.\n\n"
        f"Detection: `{_fund_check.method}` "
        f"({_fund_check.confidence*100:.0f}% confidence) — {_fund_check.detail}\n\n"
        f"For ETF analysis: etfdb.com (overlap, expense ratio, holdings), "
        f"Morningstar (fund-level metrics), your broker (NAV vs price)."
    )
    st.markdown("---")
    st.markdown("### Quick reference")
    _refs: list[tuple[str, str]] = []
    _price = (bundle.quote or {}).get("price")
    if _price:
        _refs.append(("Current price", f"${float(_price):.2f}"))
    _lo = (live_info or {}).get("fiftyTwoWeekLow") or (live_info or {}).get("fifty_two_week_low")
    _hi = (live_info or {}).get("fiftyTwoWeekHigh") or (live_info or {}).get("fifty_two_week_high")
    if _lo and _hi:
        _refs.append(("52w range", f"${float(_lo):.2f} – ${float(_hi):.2f}"))
    if _refs:
        _ref_metric_row(_refs)
    st.stop()


# ---- REIT ----
_reit_check = detect_reit(active_ticker, bundle.fmp_profile, live_info)
if _reit_check.is_reit:
    st.error(
        f"🚫 **{active_ticker}** is a **REIT** (Real Estate Investment Trust).\n\n"
        f"FCFF DCF **does not apply** to REITs because they are required "
        f"by law to distribute ≥90% of net income — they don't accumulate "
        f"capital. The DCF will produce nonsense values (typically 4–10× "
        f"the real price).\n\n"
        f"💡 **Use instead:** P/FFO (Funds From Operations), P/AFFO "
        f"(Adjusted FFO net of maintenance capex), dividend yield vs "
        f"sub-sector peers, or NAV per share.\n\n"
        f"Detection: `{_reit_check.method}` "
        f"({_reit_check.confidence*100:.0f}% confidence) — {_reit_check.detail}"
    )
    st.markdown("---")
    st.markdown("### Quick reference")
    _refs = []
    _price = (bundle.quote or {}).get("price")
    if _price:
        _refs.append(("Current price", f"${float(_price):.2f}"))
    _div = (live_info or {}).get("dividendYield")
    if _div:
        _refs.append(("Dividend yield", f"{float(_div)*100:.2f}%"))
    _mcap = (live_info or {}).get("marketCap") or (bundle.fmp_profile or {}).get("mktCap")
    if _mcap:
        _refs.append(("Market cap", f"${float(_mcap)/1e9:.1f}B"))
    if _refs:
        _ref_metric_row(_refs)
    st.stop()


# ---- Bank ----
_bank_check = detect_bank(active_ticker, bundle.fmp_profile, live_info)
if _bank_check.is_bank:
    st.error(
        f"🚫 **{active_ticker}** is a **bank**.\n\n"
        f"Banks can't be valued with FCFF DCF: their balance sheet is "
        f"dominated by deposits and loans (not working capital), 'free "
        f"cash flow' is not comparable to operating companies (their "
        f"business *is* the balance sheet), and optimal leverage is "
        f"regulated, not a management decision.\n\n"
        f"💡 **Use instead:** P/TBV (Price / Tangible Book Value — the "
        f"standard multiple), P/E adjusted by credit cycle, Residual "
        f"Income model, or DDM for stable-payout banks. Bank-specific "
        f"metrics: NIM, efficiency ratio, NPL ratio, CET1, ROE.\n\n"
        f"Detection: `{_bank_check.method}` "
        f"({_bank_check.confidence*100:.0f}% confidence) — {_bank_check.detail}"
    )
    st.markdown("---")
    st.markdown("### Quick reference")
    _refs = []
    _price = (bundle.quote or {}).get("price")
    if _price:
        _refs.append(("Current price", f"${float(_price):.2f}"))
    _pe = (live_info or {}).get("trailingPE")
    if _pe:
        _refs.append(("P/E (TTM)", f"{float(_pe):.1f}"))
    _pb = (live_info or {}).get("priceToBook")
    if _pb:
        _refs.append(("P/B", f"{float(_pb):.2f}"))
    if _refs:
        _ref_metric_row(_refs)
    st.stop()


# ============================================================
# Soft-block (P12.B2) — utility / insurance / BDC / MLP / royalty trust
# get a warning + override checkbox. Funds / REITs / banks already
# stopped above; the dict entries for them remain as a safety net in
# case a new path slips around the hard blocks.
# ============================================================
from analysis.security_classifier import classify_security, SecurityType

_sec_class = classify_security(
    ticker=active_ticker,
    sector=live_info.get("sector") if live_info else None,
    industry=live_info.get("industry") if live_info else None,
    name=live_info.get("name") if live_info else None,
)
SHOW_VALUATION = True
if not _sec_class.valuation_applicable:
    _type_label = {
        SecurityType.UTILITY:       "regulated utility",
        SecurityType.REIT:          "REIT",
        SecurityType.BANK:          "bank",
        SecurityType.INSURANCE:     "insurance company",
        SecurityType.BDC:           "BDC",
        SecurityType.MLP:           "MLP",
        SecurityType.FUND:          "ETF / fund",
        SecurityType.ROYALTY_TRUST: "royalty trust",
    }.get(_sec_class.security_type, "non-operating security")

    st.warning(
        f"🚧 **{active_ticker}** looks like a **{_type_label}** "
        f"({_sec_class.confidence*100:.0f}% confidence). "
        f"{_sec_class.reason}\n\n"
        f"The FCFF DCF model in this app **does not apply correctly** "
        f"to this kind of security and would produce misleading intrinsic "
        f"values.\n\n"
        f"💡 **Suggested approach:** "
        f"{_sec_class.suggested_alternative or 'Use sector-specific tools.'}"
    )
    _override = st.checkbox(
        "Show financial statements only (skip valuation)",
        value=False,
        key=f"sec_override_{active_ticker}",
        help="Statements still show real numbers; only the intrinsic-value "
             "engines are unreliable for this security type.",
    )
    if not _override:
        st.stop()
    SHOW_VALUATION = False


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

# Compute market-implied stage-1 growth once — the Valuation tab card
# renders this number; the snapshot DB stores it so we have a record
# of what the market was pricing at each visit.
_implied_growth_value: float | None = None
try:
    from valuation.reverse_dcf import run_reverse_dcf
    if (current_price and current_price > 0
            and results.wacc and not inc.empty):
        _ig_res = run_reverse_dcf(
            income=inc, balance=bal, cash=cf,
            target_price=float(current_price),
            wacc=results.wacc.wacc,
            terminal_growth=current_assumptions.terminal_growth,
            stage1_years=current_assumptions.stage1_years,
            stage2_years=current_assumptions.stage2_years,
        )
        if _ig_res and _ig_res.implied_growth is not None and np.isfinite(_ig_res.implied_growth):
            _implied_growth_value = float(_ig_res.implied_growth)
except Exception:
    _implied_growth_value = None

# Auto-snapshot of analysis state (P11.B4 + P7.7). Dedupe by financials
# hash — re-opening the same ticker in the same day is a no-op. New
# snapshot only when SEC ships a restatement or financials roll forward.
try:
    from data.snapshot_db import save_snapshot
    save_snapshot(
        ticker=active_ticker,
        bundle=bundle,
        intrinsic=(results.aggregator.intrinsic_per_share
                   if results.aggregator
                   and np.isfinite(results.aggregator.intrinsic_per_share)
                   else None),
        implied_growth=_implied_growth_value,
    )
except Exception:
    pass

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
_fin_chip = source_chip(bundle.financials_source if bundle else "—")
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
render_company_profile(
    active_ticker,
    live_info=bundle.info,
    fmp_profile=bundle.fmp_profile,
)

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
    # SEC EDGAR doesn't ship a single `totalDebt` XBRL element — fall
    # back to longTermDebt + shortTermDebt (either of which may be
    # absent). Subtracting cash to reach net debt is technically more
    # accurate but EV proxy without cash is the convention here.
    if market_cap_pr is not None:
        try:
            debt_proxy = 0.0
            for col in ("totalDebt", "longTermDebt", "shortTermDebt",
                        "currentPortionOfLongTermDebt"):
                if col in bal.columns:
                    v = bal[col].iloc[-1]
                    if pd.notna(v):
                        debt_proxy += float(v)
                        if col == "totalDebt":
                            break
            enterprise_value_pr = market_cap_pr + debt_proxy
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

(tab_overview, tab_valuation, tab_financials, tab_forecast, tab_ratios,
 tab_quality, tab_peers, tab_capital, tab_insiders,
 tab_charts) = st.tabs([
    "Overview", "Valuation", "Financials", "Forecast", "Ratios",
    "Quality", "Peers", "Capital allocation", "Insiders",
    "Charts",
])


# ---- Overview ----
with tab_overview:
    # ---- 0. Company context card (one-glance summary) ----
    from ui.components.company_context_card import render_company_context_card
    render_company_context_card(
        ticker=active_ticker,
        name=(live_info.get("name")
              or live_info.get("longName")
              or TICKER_META.get(active_ticker, {}).get("name")),
        sector=(live_info.get("sector")
                or TICKER_META.get(active_ticker, {}).get("sector")),
        industry=(live_info.get("industry")
                  or TICKER_META.get(active_ticker, {}).get("industry")),
        description=(live_info.get("longBusinessSummary")
                     or live_info.get("description")
                     or (bundle.fmp_profile or {}).get("description")),
        peers=[p.ticker for p in (peers_demo or [])],
    )
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

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

    # News & Sentiment removed (P10.5) — the user reads news directly
    # from the source. The components and analyzers (news_combined_section,
    # news_sentiment, news_sentiment_panel) remain in git for reactivation
    # if desired.

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

    # AI thesis panel disconnected from UI (PROMPT 9 PARTE 3) — modules
    # `analysis.ai_thesis_prompt` and `ui.components.ai_thesis_panel`
    # remain in git for future revisit with stricter guardrails.

    st.caption(
        "Pending live-data wiring: segments / geography, analyst ratings, "
        "short interest, events timeline. They land when the FMP / EDGAR "
        "endpoints come online."
    )


# ---- Valuation ----
with tab_valuation:
    if not SHOW_VALUATION:
        st.info(
            f"Valuation skipped — {active_ticker} is a "
            f"{_type_label}, the FCFF DCF doesn't apply. "
            f"💡 {_sec_class.suggested_alternative or ''}"
        )
        st.stop()

    # Market-implied growth header card — the page-level _implied_growth_value
    # was already computed above for the snapshot save, so we re-render
    # via the same path (the inner reverse_dcf call hits a cheap
    # short-circuit when called twice in a row).
    from ui.components.market_implied_growth_card import (
        render_market_implied_growth_card,
    )
    render_market_implied_growth_card(
        income=inc, balance=bal, cash=cf,
        current_price=current_price,
        wacc=results.wacc.wacc if results.wacc else None,
        terminal_growth=current_assumptions.terminal_growth,
        stage1_years=current_assumptions.stage1_years,
        stage2_years=current_assumptions.stage2_years,
    )

    # Per-model cards
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'MODEL CONTRIBUTIONS</div>',
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
        g_override = current_assumptions.override_growth
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

    # ---- Position sizing helper (P11.B3) ----
    from ui.components.position_sizing_card import render_position_sizing_card
    render_position_sizing_card(active_ticker, current_price)

    # ---- Multi-multiple forward valuation (cross-check via peers) ----
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">MULTI-MULTIPLE VALUATION · '
        'PEERS × FORWARD</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Implied price applying peer-median multiples to your forecast. "
        "Cross-check to the DCF — divergence between models is signal."
    )
    _shares_for_mm = (
        live_info.get("sharesOutstanding")
        or live_info.get("shares_outstanding")
        if isinstance(live_info, dict) else None
    )
    if _shares_for_mm and peers_demo:
        try:
            from analysis.financial_forecast import (
                _default_inputs_from_history, project_financials,
            )
            from ui.components.multi_multiple_valuation import (
                render_multi_multiple_valuation_panel,
            )
            _mm_inputs = _default_inputs_from_history(inc, bal, cf, years=5)
            _mm_forecast = project_financials(
                inc, bal, cf, inputs=_mm_inputs, years=5,
                shares_outstanding=_shares_for_mm,
            )
            render_multi_multiple_valuation_panel(
                target_ticker=active_ticker,
                current_price=current_price,
                forecast_result=_mm_forecast,
                peer_snapshots=peers_demo,
                shares_outstanding=_shares_for_mm,
                discount_rate=0.12,
            )
        except Exception as exc:
            st.warning(f"Multi-multiple valuation failed: {exc}")
    elif not _shares_for_mm:
        st.info(
            "Multi-multiple valuation needs shares outstanding "
            "(unavailable from the data sources for this ticker)."
        )
    else:
        st.info(
            "Multi-multiple valuation needs peers — none configured "
            "for this ticker."
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
            options=["Analyst", "Absolute", "Common size", "Growth"],
            index=0, horizontal=True, label_visibility="collapsed",
            key=f"fin_view_{active_ticker}",
        )
    view_mode = {
        "Analyst":      "hybrid",
        "Absolute":     "absolute",
        "Common size":  "common_size",
        "Growth":       "growth",
    }[view_mode_label]

    # Quarterly statements for TTM column (hybrid view only)
    inc_q = bal_q = cf_q = None
    if view_mode == "hybrid":
        try:
            from data.fmp_provider import FMPProvider
            _fmp = FMPProvider()
            inc_q = _fmp.fetch_income_statement_quarterly(active_ticker)
            bal_q = _fmp.fetch_balance_sheet_quarterly(active_ticker)
            cf_q = _fmp.fetch_cash_flow_quarterly(active_ticker)
        except Exception:
            pass            # TTM cells will render as "—"

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
    inc5  = _dedup_and_cap_years(inc)
    bal5  = _dedup_and_cap_years(bal)
    cf5   = _dedup_and_cap_years(cf)

    st.plotly_chart(
        build_income_chart(inc5, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_income_statement(inc5, view=view_mode, quarterly=inc_q)

    # ---- Balance Sheet ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'BALANCE SHEET</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_balance_chart(bal5, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_balance_sheet(bal5, view=view_mode, quarterly=bal_q)

    # ---- Cash Flow ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'CASH FLOW STATEMENT</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_fcf_chart(cf5, income=inc5, height=200),
        use_container_width=True, config={"displayModeBar": False},
    )
    render_cash_flow(cf5, view=view_mode, quarterly=cf_q)

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

    # Drop duplicate filings + cap to the same 5-year window the
    # statements above use, so the panels stay aligned.
    ratios_capped = _dedup_and_cap_years(ratios)
    transposed = ratios_capped[show_cols].T

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


# ---- Forecast ----
@st.fragment
def _forecast_tab_fragment(inc, bal, cf, live_info, current_price):
    """st.fragment isolates this tab's re-renders from the rest of the
    page. Moving a slider on the DCF panel won't recompute the forecast
    here, and vice versa. Big perf win on the heavier tabs."""
    from ui.components.forecast_panel import render_forecast_panel
    _shares = None
    if isinstance(live_info, dict):
        _shares = (live_info.get("sharesOutstanding")
                   or live_info.get("shares_outstanding"))
    render_forecast_panel(
        income=inc, balance=bal, cash=cf,
        shares_outstanding=_shares,
        current_price=current_price,
    )


with tab_forecast:
    _forecast_tab_fragment(inc, bal, cf, live_info, current_price)


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
@st.fragment
def _quality_tab_fragment(inc, bal, cf, eq, active_ticker, sector_label):
    """Quality tab is one of the heaviest (Beneish/Piotroski/Sloan +
    BS forensics + revenue quality + earnings volatility + ESG fetch).
    Wrapping in @st.fragment isolates re-renders so a slider move on
    the DCF panel doesn't recompute every model here."""
    from ui.components.quality_checklist_card import render_quality_checklist
    from ui.components.balance_sheet_forensics_card import render_balance_sheet_forensics
    from ui.components.revenue_quality_card import render_revenue_quality_card
    from ui.components.earnings_volatility_card import render_earnings_volatility_card
    from ui.components.esg_panel import render_esg_panel
    from ui.components.forensic_flags_card import render_forensic_flags
    from analysis.forensics import run_all_checks
    from analysis.quality import (
        analyze_balance_sheet_quality, analyze_revenue_quality,
    )
    from analysis.earnings_volatility import analyze_earnings_volatility

    # Forensic flags first — this is the "what should worry me?" view.
    # Empty list renders the "all clear" green banner (P7.4).
    render_forensic_flags(run_all_checks(inc, bal, cf))
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

    # Phil-Town / Pat-Dorsey style quality checklist (positives view)
    render_quality_checklist(inc, bal, cf)
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

    # Sloan ratio (accruals quality) is one number, easy to read. Beneish +
    # Piotroski were dropped in P11.A4 — the analysis code stays in
    # earnings_quality.py so callers can still invoke them programmatically,
    # but the academic-card UI is gone (Quality Checklist + forensic flags
    # cover the same ground in plain English).
    if eq.sloan is not None:
        sloan_color = ("#10B981" if eq.sloan.flag == "green"
                       else "#B87333" if eq.sloan.flag == "yellow"
                       else "#DC2626")
        st.markdown(
            '<div style="background:var(--surface); border-left:3px solid '
            f'{sloan_color}; padding:12px 16px; border-radius:6px; '
            'margin-top:14px;">'
            '<div style="color:var(--text-muted); font-size:11px; '
            'text-transform:uppercase; letter-spacing:0.6px;">'
            'Sloan accruals ratio</div>'
            f'<div style="color:var(--text-primary); font-size:18px; '
            f'font-weight:500; margin-top:4px; '
            f'font-variant-numeric:tabular-nums;">{eq.sloan.score:.3f}</div>'
            '<div style="color:var(--text-secondary); font-size:11px; '
            'margin-top:4px;">Higher accruals → more "paper" earnings vs '
            'cash. Threshold ±0.10 is the conventional flag.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    bs_res = analyze_balance_sheet_quality(income=inc, balance=bal)
    render_balance_sheet_forensics(bs_res)

    industry_label = TICKER_META.get(active_ticker, {}).get("industry")
    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    rev_q = analyze_revenue_quality(
        income=inc, sector=sector_label, industry=industry_label,
    )
    render_revenue_quality_card(rev_q)

    st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
    ev_res = analyze_earnings_volatility(income=inc)
    render_earnings_volatility_card(ev_res)

    render_esg_panel(active_ticker)


with tab_quality:
    _quality_tab_fragment(inc, bal, cf, eq, active_ticker, sector_label)


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
# Heavy: SEC EDGAR Form 4 parsing can take 1-3 minutes. Gate behind an
# explicit button (P10.7) so opening the Insiders tab doesn't block the
# page on a request the user might not want. Once loaded, results stay
# in session_state so subsequent visits are instant.
with tab_insiders:
    sub_corp, sub_gov = st.tabs([
        "Corporate insiders (Form 4)", "Government trades",
    ])

    _ins_load_key = f"_ins_loaded_{active_ticker}"

    with sub_corp:
        if st.session_state.get(_ins_load_key):
            from analysis.insider_analysis import analyze_insider_activity
            from analysis.etf_analysis import analyze_etf_holdings
            from ui.components.insider_panel import render_insider_panel
            from ui.components.etf_holdings_panel import render_etf_holdings_panel
            from ui.components.sec_insiders_panel import render_sec_insiders_panel

            render_sec_insiders_panel(active_ticker)

            st.markdown("<div style='height:22px;'></div>",
                        unsafe_allow_html=True)
            insider_res = analyze_insider_activity(active_ticker, months=24)
            render_insider_panel(insider_res)

            st.markdown("<div style='height:22px;'></div>",
                        unsafe_allow_html=True)
            etf_res = analyze_etf_holdings(active_ticker)
            render_etf_holdings_panel(etf_res)

            if st.button("🔄 Refresh insider data",
                         key=f"refresh_ins_{active_ticker}",
                         type="secondary"):
                st.session_state[_ins_load_key] = False
                st.rerun()
        else:
            st.markdown(
                '<div style="background:var(--surface); '
                'border:1px dashed var(--border-hover); '
                'border-radius:8px; padding:24px; text-align:center;">'
                '<div style="color:var(--text-secondary); font-size:13px; '
                'margin-bottom:12px;">'
                '🐢 Insider data parses every Form 4 filing from SEC EDGAR.'
                '<br>Estimated time: <b>1–3 minutes</b> '
                '(cached for the rest of the session after first load).'
                '</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Load insider history",
                         key=f"load_ins_{active_ticker}", type="primary"):
                st.session_state[_ins_load_key] = True
                st.rerun()

    with sub_gov:
        from ui.components.senate_trading_panel import render_senate_trading_panel
        render_senate_trading_panel(active_ticker)


# ---- Charts ----
@st.fragment
def _charts_tab_fragment(inc, bal, cf):
    """Charts tab is the heaviest renderer — 6+ Plotly figures. Wrapped
    in @st.fragment so it doesn't re-execute when sliders elsewhere move."""
    from ui.charts.profitability_evolution import build_profitability_evolution
    from ui.charts.debt_evolution import build_debt_evolution
    from ui.charts.capital_allocation_stacked import build_capital_allocation_chart
    from ui.charts.owner_earnings import build_owner_earnings_chart
    from ui.charts.cash_conversion_cycle import (
        build_ccc_chart, build_ccc_breakdown_table,
    )

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

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'PROFITABILITY EVOLUTION · ROIC / ROCE / ROA</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_profitability_evolution(inc, bal, cf, height=360),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'FINANCIAL DEBT EVOLUTION</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_debt_evolution(inc, bal, cf, height=360),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'CAPITAL ALLOCATION</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_capital_allocation_chart(inc, bal, cf, height=360),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'OWNER EARNINGS · BUFFETT-STYLE</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_owner_earnings_chart(inc, bal, cf, height=360),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'CASH CONVERSION CYCLE · DSO / DIO / DPO</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        build_ccc_chart(inc, bal, height=360),
        use_container_width=True, config={"displayModeBar": False},
    )
    _ccc_table = build_ccc_breakdown_table(inc, bal)
    if not _ccc_table.empty:
        with st.expander("CCC breakdown by year"):
            st.dataframe(_ccc_table, use_container_width=True)


with tab_charts:
    _charts_tab_fragment(inc, bal, cf)


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
