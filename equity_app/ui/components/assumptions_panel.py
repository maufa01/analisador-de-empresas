"""
ASSUMPTIONS panel — premium one-page layout.

Sections (top → bottom):
    1. Preset selector + counter (above the expander)
    2. Live header                — WACC + Cost of Equity + Save / Reset
    3. Valuation Drivers          — risk-free, ERP, terminal growth (sliders)
    4. Growth Profile             — historical CAGR vs custom override + horizons
    5. Capital Structure (expander) — beta, cost of debt, tax, equity %, bar
    6. Monte Carlo (expander)     — sims, σ rev growth, σ WACC, terminal band

Why sliders for the top-3 drivers: the user spec calls them out as the
inputs that move 80% of the result, and sliders surface the realistic
range visually (anti-fat-finger). Number inputs survive in expanders
where precision matters more than range hinting.

The panel keeps the same public signature so the page-side wiring is
untouched. No yfinance fetches happen inside the panel — reference
values come from constants + ``@st.cache_data`` helpers, so dragging a
slider stays fast.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Optional

import streamlit as st

from analysis.assumptions import (
    Assumptions, apply_preset, modified_fields, PRESETS,
)
from analysis.wacc import calculate_wacc
from core.constants import DEFAULT_WACC_PARAMS
from ui.components.capital_structure_bar import render_capital_structure_bar
from ui.components.preset_selector import render_preset_selector, force_custom


_DOT = (
    "<span title='Modified vs base' "
    "style='display:inline-block; width:6px; height:6px; "
    "border-radius:50%; background:var(--accent); margin-left:6px; "
    "vertical-align:middle;'></span>"
)


# ============================================================
# Cached reference fetchers (NOT called per-keystroke)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def _us_10y_yield_pct() -> Optional[float]:
    """Live US 10Y from yfinance, cached for an hour. None on failure."""
    try:
        import yfinance as yf
        df = yf.Ticker("^TNX").history(period="5d")
        if df is None or df.empty:
            return None
        return float(df["Close"].dropna().iloc[-1])
    except Exception:
        return None


# ============================================================
# Helpers
# ============================================================
def _label(text: str, *, modified: bool = False) -> str:
    return f"{text}{_DOT if modified else ''}"


def _safe_default(value, min_val: float, max_val: float,
                   *, fallback: Optional[float] = None) -> float:
    """Clamp ``value`` into ``[min_val, max_val]``, with a fallback for
    NaN / None / out-of-range. Streamlit's ``st.number_input`` and
    ``st.slider`` raise ``StreamlitValueAboveMaxError`` (or below-min)
    when the *initial* ``value=`` falls outside its range — common when
    a default is computed from a volatile ticker (e.g. revenue σ for
    NVDA can exceed 0.50).
    """
    import math
    if value is None:
        return float(fallback if fallback is not None else min_val)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(fallback if fallback is not None else min_val)
    if math.isnan(v) or math.isinf(v):
        return float(fallback if fallback is not None else min_val)
    return float(max(min_val, min(v, max_val)))


def _live_wacc(a: Assumptions) -> Optional[float]:
    try:
        w = calculate_wacc(
            risk_free=a.risk_free, equity_risk_premium=a.equity_risk_premium,
            beta=a.beta, cost_of_debt_pretax=a.cost_of_debt,
            tax_rate=a.tax_rate,
            weight_equity=a.weight_equity, weight_debt=a.weight_debt,
        )
        return float(w.wacc)
    except Exception:
        return None


def _cost_of_equity(a: Assumptions) -> float:
    return a.risk_free + a.beta * a.equity_risk_premium


def _restore_or_init_state(ticker: str, base: Assumptions) -> Assumptions:
    base_key = f"assumptions_{ticker}_base"
    user_key = f"assumptions_{ticker}_user"
    st.session_state[base_key] = base.to_dict()
    if user_key not in st.session_state:
        st.session_state[user_key] = base.to_dict()
        return replace(base, warnings=list(base.warnings))
    return Assumptions.from_dict(st.session_state[user_key])


def _persist(ticker: str, current: Assumptions) -> None:
    st.session_state[f"assumptions_{ticker}_user"] = current.to_dict()


def _live_header(
    *, wacc: Optional[float], cost_of_equity: float,
    n_modified: int,
) -> None:
    """Render the four-cell live preview strip."""
    wacc_str = f"{wacc*100:.2f}%" if wacc is not None else "—"
    coe_str = f"{cost_of_equity*100:.2f}%"
    badge = (
        f'<span style="color:var(--accent); font-size:11px; '
        f'letter-spacing:0.4px; margin-left:8px;">'
        f'· {n_modified} modified</span>' if n_modified else ""
    )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px;">'
        '<div style="display:flex; gap:32px; flex-wrap:wrap;">'
        '<div>'
        '<div class="eq-idx-label">WACC</div>'
        '<div style="color:var(--text-primary); font-size:24px; '
        'font-weight:500; font-variant-numeric:tabular-nums; '
        f'letter-spacing:-0.4px; margin-top:4px;">{wacc_str}</div></div>'
        '<div>'
        '<div class="eq-idx-label">COST OF EQUITY</div>'
        '<div style="color:var(--text-primary); font-size:24px; '
        'font-weight:500; font-variant-numeric:tabular-nums; '
        f'letter-spacing:-0.4px; margin-top:4px;">{coe_str}</div></div>'
        '<div style="margin-left:auto; align-self:center;">'
        f'<span style="color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.4px;">live preview</span>{badge}'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Public API — same signature as before
# ============================================================
def render_assumptions_panel(
    *,
    ticker: str,
    base: Assumptions,
    expanded: bool = True,
    on_save=None,
    on_reset=None,
) -> Assumptions:
    """
    Render the panel and return the current ``Assumptions`` after the
    user's edits this run. Public signature unchanged from the previous
    layout — page wiring need not be touched.
    """
    preset_key = f"preset_{ticker}"

    # ---- Preset selector — collapsed by default (P10.4). The Base case
    # radio is the 99% path; Bull / Bear / Custom only when the user
    # explicitly opens the expander to compare scenarios.
    counter_slot = st.empty()
    with st.expander("⚙ Advanced — multi-scenario (Bull / Bear / Custom)",
                     expanded=False):
        st.caption(
            "Default is the **Base case**. Switch to Bull / Bear to "
            "stress assumptions ±20% growth and margins. Custom unlocks "
            "every individual slider below."
        )
        preset = render_preset_selector(default="Base case", key=preset_key)

    # Apply non-Custom preset
    if preset != "Custom":
        derived = apply_preset(base, preset)
        if (st.session_state.get(f"_last_preset_{ticker}") != preset
                or f"assumptions_{ticker}_user" not in st.session_state):
            st.session_state[f"assumptions_{ticker}_user"] = derived.to_dict()
            st.session_state[f"_last_preset_{ticker}"] = preset

    current = _restore_or_init_state(ticker, base)
    diff = modified_fields(current, base)
    n_mod = len(diff)
    counter_slot.markdown(
        f'<div style="text-align:right; padding-top:6px; '
        f'color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.4px;">'
        f'{n_mod} value{"" if n_mod == 1 else "s"} modified</div>',
        unsafe_allow_html=True,
    )

    # ---- Header label ----
    header_label = (
        "⚙  ASSUMPTIONS  ·  Click to adjust valuation inputs"
        + (f"  ·  {n_mod} modified" if n_mod else "")
    )

    with st.expander(header_label, expanded=expanded):
        # Live preview header
        _live_header(
            wacc=_live_wacc(current),
            cost_of_equity=_cost_of_equity(current),
            n_modified=n_mod,
        )

        # Save / Reset row
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        sl, sm, sr = st.columns([5, 1, 1])
        with sm:
            if st.button("Save", key=f"save_assumptions_{ticker}",
                         use_container_width=True,
                         help="Persist these assumptions for this ticker."):
                if on_save is not None:
                    on_save(current)
                    st.toast(f"Assumptions saved for {ticker}.", icon="💾")
        with sr:
            if st.button("Reset", key=f"reset_assumptions_{ticker}",
                         use_container_width=True,
                         help="Discard custom edits and reload the base case."):
                st.session_state[f"assumptions_{ticker}_user"] = base.to_dict()
                st.session_state[preset_key] = "Base case"
                if on_reset is not None:
                    on_reset()
                st.rerun()

        # ============================================================
        # SECTION 1 — VALUATION DRIVERS (sliders)
        # ============================================================
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'VALUATION DRIVERS · 3 inputs that move ~80% of the result'
            '</div>',
            unsafe_allow_html=True,
        )

        d1, d2, d3 = st.columns(3, gap="medium")

        with d1:
            ten_y = _us_10y_yield_pct()
            ref_rf = (f"US 10Y currently {ten_y:.2f}%"
                      if ten_y is not None else "Default: US 10Y Treasury")
            st.markdown(
                '<div style="font-size:13px; font-weight:500; '
                'color:var(--text-primary);">Risk-free rate</div>'
                '<div style="font-size:10px; color:var(--text-muted); '
                'letter-spacing:0.3px;">CAPM input — Re anchor</div>',
                unsafe_allow_html=True,
            )
            new_rf = st.slider(
                _label("rf", modified="risk_free" in diff),
                min_value=0.01, max_value=0.08,
                value=_safe_default(current.risk_free, 0.01, 0.08, fallback=0.045),
                step=0.0025,
                format="%.4f", label_visibility="collapsed",
                key=f"rf_{ticker}",
            )
            st.caption(ref_rf)

        with d2:
            st.markdown(
                '<div style="font-size:13px; font-weight:500; '
                'color:var(--text-primary);">Equity risk premium</div>'
                '<div style="font-size:10px; color:var(--text-muted); '
                'letter-spacing:0.3px;">Excess return vs risk-free</div>',
                unsafe_allow_html=True,
            )
            new_erp = st.slider(
                _label("erp", modified="equity_risk_premium" in diff),
                min_value=0.03, max_value=0.08,
                value=_safe_default(current.equity_risk_premium, 0.03, 0.08, fallback=0.055),
                step=0.0025,
                format="%.4f", label_visibility="collapsed",
                key=f"erp_{ticker}",
            )
            st.caption(
                f"Damodaran USA: {DEFAULT_WACC_PARAMS['market_risk_premium']*100:.2f}%"
            )

        with d3:
            st.markdown(
                '<div style="font-size:13px; font-weight:500; '
                'color:var(--text-primary);">Terminal growth</div>'
                '<div style="font-size:10px; color:var(--text-muted); '
                'letter-spacing:0.3px;">Long-run perpetuity rate</div>',
                unsafe_allow_html=True,
            )
            new_g_t = st.slider(
                _label("gt", modified="terminal_growth" in diff),
                min_value=0.005, max_value=0.045,
                value=_safe_default(current.terminal_growth, 0.005, 0.045, fallback=0.025),
                step=0.0025,
                format="%.4f", label_visibility="collapsed",
                key=f"gt_{ticker}",
            )
            st.caption("Cap: long-term GDP / inflation (~2.5%)")

        # ============================================================
        # SECTION 2 — GROWTH PROFILE
        # ============================================================
        st.markdown(
            '<div class="eq-section-label" style="margin-top:18px;">'
            'GROWTH PROFILE</div>',
            unsafe_allow_html=True,
        )

        # override_growth is Optional[float]: None ⇒ use historical CAGR.
        use_custom = current.override_growth is not None
        choice = st.radio(
            "growth_choice",
            options=("Use historical FCF CAGR", "Override with custom growth"),
            index=1 if use_custom else 0,
            horizontal=True, label_visibility="collapsed",
            key=f"growth_choice_{ticker}",
        )

        if choice == "Use historical FCF CAGR":
            new_g1 = None
            st.caption("Stage-1 growth derived from realised FCF CAGR (clipped to ±30%).")
        else:
            seed = (float(current.override_growth)
                    if current.override_growth is not None else 0.05)
            new_g1 = st.slider(
                _label("Custom stage-1 growth (annualised)",
                       modified="override_growth" in diff),
                min_value=-0.05, max_value=0.30,
                value=_safe_default(seed, -0.05, 0.30, fallback=0.05),
                step=0.0025, format="%.4f",
                key=f"gov_{ticker}",
            )

        h1, h2 = st.columns(2, gap="medium")
        with h1:
            new_s1 = int(st.slider(
                _label("High-growth period (years)",
                       modified="stage1_years" in diff),
                min_value=2, max_value=10,
                value=int(_safe_default(current.stage1_years, 2, 10, fallback=5)),
                step=1, key=f"s1_{ticker}",
            ))
        with h2:
            new_s2 = int(st.slider(
                _label("Fade period (years)",
                       modified="stage2_years" in diff),
                min_value=0, max_value=10,
                value=int(_safe_default(current.stage2_years, 0, 10, fallback=5)),
                step=1, key=f"s2_{ticker}",
            ))

        # ============================================================
        # SECTION 3 — CAPITAL STRUCTURE & COST OF CAPITAL (expander)
        # ============================================================
        with st.expander("Capital structure & cost of capital",
                         expanded=False):
            st.caption(
                "Beta defaults to a 5y monthly OLS vs S&P 500. Cost of debt "
                "is interest expense / average total debt. Tax rate is the "
                "3y effective rate. The capital mix below comes from market "
                "cap / total debt."
            )

            c1, c2, c3 = st.columns(3, gap="small")
            with c1:
                new_beta = st.number_input(
                    _label("Beta", modified="beta" in diff),
                    value=_safe_default(current.beta, 0.30, 2.50, fallback=1.0),
                    min_value=0.30, max_value=2.50,
                    step=0.05, format="%.2f",
                    key=f"beta_{ticker}",
                )
            with c2:
                new_cod = st.number_input(
                    _label("Cost of debt (pre-tax)",
                           modified="cost_of_debt" in diff),
                    value=_safe_default(current.cost_of_debt, 0.005, 0.10, fallback=0.04),
                    min_value=0.005, max_value=0.10,
                    step=0.0025, format="%.4f",
                    key=f"cod_{ticker}",
                )
            with c3:
                new_tax = st.number_input(
                    _label("Tax rate", modified="tax_rate" in diff),
                    value=_safe_default(current.tax_rate, 0.0, 0.45, fallback=0.21),
                    min_value=0.0, max_value=0.45,
                    step=0.005, format="%.4f",
                    key=f"tax_{ticker}",
                )

            st.markdown("<div style='height:10px;'></div>",
                        unsafe_allow_html=True)
            new_we = st.slider(
                _label("Equity weight", modified="weight_equity" in diff),
                min_value=0.05, max_value=0.99,
                value=_safe_default(current.weight_equity, 0.05, 0.99, fallback=0.7),
                step=0.01, format="%.2f",
                key=f"we_{ticker}",
            )
            st.markdown(
                '<div style="color:var(--text-muted); font-size:11px; '
                'letter-spacing:0.4px; margin-top:4px;">'
                f'EQUITY <b style="color:var(--text-primary);">{new_we*100:.1f}%</b>'
                f' &nbsp;·&nbsp; DEBT <b style="color:var(--text-primary);">'
                f'{(1.0-new_we)*100:.1f}%</b></div>',
                unsafe_allow_html=True,
            )
            render_capital_structure_bar(weight_equity=new_we)

        # ============================================================
        # SECTION 4 — MONTE CARLO (expander)
        # ============================================================
        with st.expander("Monte Carlo parameters (advanced)",
                         expanded=False):
            st.caption(
                "Probability distributions for the Monte Carlo DCF. "
                "Defaults derived from the company's revenue dispersion."
            )
            m1, m2 = st.columns(2, gap="small")
            with m1:
                new_n = int(st.slider(
                    _label("Simulations", modified="mc_n_simulations" in diff),
                    min_value=500, max_value=20_000,
                    value=int(_safe_default(current.mc_n_simulations,
                                            500, 20_000, fallback=10_000)),
                    step=500,
                    key=f"mcn_{ticker}",
                ))
                # max raised from 0.30 → 1.0 because high-growth tickers
                # (NVDA, TSLA, recent IPOs) routinely show revenue σ > 50%.
                new_revstd = st.number_input(
                    _label("Revenue growth σ",
                           modified="mc_rev_growth_std" in diff),
                    value=_safe_default(current.mc_rev_growth_std,
                                        0.005, 1.0, fallback=0.10),
                    min_value=0.005, max_value=1.0,
                    step=0.005, format="%.4f",
                    key=f"mcrs_{ticker}",
                    help=(f"Historical default: {current.mc_rev_growth_std*100:.1f}%"
                          if current.mc_rev_growth_std else "No historical data"),
                )
            with m2:
                new_wstd = st.number_input(
                    _label("WACC σ", modified="mc_wacc_std" in diff),
                    value=_safe_default(current.mc_wacc_std,
                                        0.0005, 0.020, fallback=0.005),
                    min_value=0.0005, max_value=0.020,
                    step=0.0005, format="%.4f",
                    key=f"mcws_{ticker}",
                )
                band_lo = _safe_default(current.mc_terminal_low, 0.0, 0.06, fallback=0.015)
                band_hi = _safe_default(current.mc_terminal_high, 0.0, 0.06, fallback=0.035)
                if band_lo > band_hi:
                    band_lo, band_hi = band_hi, band_lo
                band = st.slider(
                    _label("Terminal growth band",
                           modified=("mc_terminal_low" in diff
                                     or "mc_terminal_high" in diff)),
                    min_value=0.0, max_value=0.06,
                    value=(band_lo, band_hi),
                    step=0.0025, format="%.3f",
                    key=f"mctb_{ticker}",
                )
                new_t_low, new_t_high = float(band[0]), float(band[1])

    # ---- Build the updated assumptions ----
    updated = replace(
        current,
        beta=float(new_beta),
        risk_free=float(new_rf),
        equity_risk_premium=float(new_erp),
        cost_of_debt=float(new_cod),
        tax_rate=float(new_tax),
        weight_equity=float(new_we),
        stage1_years=int(new_s1),
        stage2_years=int(new_s2),
        terminal_growth=float(new_g_t),
        override_growth=(None if new_g1 is None else float(new_g1)),
        mc_n_simulations=int(new_n),
        mc_rev_growth_std=float(new_revstd),
        mc_wacc_std=float(new_wstd),
        mc_terminal_low=float(new_t_low),
        mc_terminal_high=float(new_t_high),
    )

    _persist(ticker, updated)

    # If the user edited something while a non-Custom preset was active,
    # flip the selector to Custom on the NEXT rerun.
    new_diff = modified_fields(updated, apply_preset(base, preset))
    if new_diff and preset != "Custom":
        force_custom(preset_key)

    return updated
