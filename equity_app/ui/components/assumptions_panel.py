"""
ASSUMPTIONS panel — the inline expander that replaces the WACC sidebar.

Layout
------
Header row     : preset selector (Base/Bull/Bear/Custom) + computed
                 WACC badge + modification counter + Save / Reset buttons
3-column body  : WACC components | Capital structure | Projection
Bottom row     : Monte Carlo inputs (4 columns)

Returns the current ``Assumptions`` dataclass with whatever overrides
the user has applied. The page passes that into ``run_valuation``.

Per-ticker session state
------------------------
- ``assumptions_{ticker}_user`` : dict of the user's current edits
- ``assumptions_{ticker}_base`` : dict of the BASE-case defaults

Switching presets re-derives the panel values from the base case via
``apply_preset``; user edits afterwards flip the preset to "Custom" and
add a gold dot next to the modified inputs.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Optional

import streamlit as st

from analysis.assumptions import (
    Assumptions, apply_preset, modified_fields, PRESETS,
)
from analysis.wacc import calculate_wacc
from ui.components.capital_structure_bar import render_capital_structure_bar
from ui.components.preset_selector import render_preset_selector, force_custom


_DOT = (
    "<span title='Modified vs base' "
    "style='display:inline-block; width:6px; height:6px; "
    "border-radius:50%; background:var(--accent); margin-left:6px; "
    "vertical-align:middle;'></span>"
)


# ============================================================
# Helpers
# ============================================================
def _label(text: str, *, modified: bool = False) -> str:
    """Returns the inline HTML for an input label with optional gold dot."""
    dot = _DOT if modified else ""
    return f"{text}{dot}"


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


def _restore_or_init_state(ticker: str, base: Assumptions) -> Assumptions:
    """
    Hydrate the panel's working ``Assumptions`` from session state, falling
    back to the freshly-computed base case when nothing is stored yet.
    """
    base_key = f"assumptions_{ticker}_base"
    user_key = f"assumptions_{ticker}_user"

    st.session_state[base_key] = base.to_dict()
    if user_key not in st.session_state:
        st.session_state[user_key] = base.to_dict()
        return replace(base, warnings=list(base.warnings))

    return Assumptions.from_dict(st.session_state[user_key])


def _persist(ticker: str, current: Assumptions) -> None:
    st.session_state[f"assumptions_{ticker}_user"] = current.to_dict()


# ============================================================
# Public API
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
    Render the panel and return the current ``Assumptions`` after any
    user edits this run.

    Args:
        ticker:    used to namespace session state per company
        base:      base-case Assumptions computed from the financials
        expanded:  initial state of the expander (True the first run,
                   False once the user has clicked through)
        on_save:   optional callback(Assumptions) — wired to the
                   "Save current assumptions" button (typically writes
                   to user_assumptions_db)
        on_reset:  optional callback() — fires after the panel resets
                   to the base case (lets the caller clear DB rows)
    """
    preset_key = f"preset_{ticker}"

    # ---- Preset selector + count badge (above the expander) ----
    psel_l, psel_r = st.columns([3, 2])
    with psel_l:
        preset = render_preset_selector(default="Base case", key=preset_key)
    with psel_r:
        # Live counter — populated after we know which fields are modified
        counter_slot = st.empty()

    # ---- Apply the preset to the base case ----
    if preset != "Custom":
        # Switching to a non-custom preset wipes any prior user edits.
        derived = apply_preset(base, preset)
        if (st.session_state.get(f"_last_preset_{ticker}") != preset
                or f"assumptions_{ticker}_user" not in st.session_state):
            st.session_state[f"assumptions_{ticker}_user"] = derived.to_dict()
            st.session_state[f"_last_preset_{ticker}"] = preset

    current = _restore_or_init_state(ticker, base)

    # Recompute the diff so we can decorate labels and the counter
    diff = modified_fields(current, base)
    n_mod = len(diff)
    counter_slot.markdown(
        f'<div style="text-align:right; padding-top:6px; '
        f'color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.4px;">'
        f'{n_mod} value{"" if n_mod == 1 else "s"} modified</div>',
        unsafe_allow_html=True,
    )

    # ---- Header inside the expander: WACC badge + Save / Reset ----
    live_wacc = _live_wacc(current)
    wacc_badge = (
        f"WACC <b style='color:var(--text-primary);'>{live_wacc:.2%}</b>"
        if live_wacc is not None else "WACC —"
    )
    header_label = (
        f"⚙  ASSUMPTIONS  ·  Click to adjust valuation inputs"
        + (f"  ·  {n_mod} modified" if n_mod else "")
    )

    with st.expander(header_label, expanded=expanded):
        # In-expander header: live WACC + Save + Reset
        h1, h2, h3 = st.columns([3, 1, 1])
        with h1:
            st.markdown(
                f'<div style="color:var(--text-secondary); font-size:13px; '
                f'padding-top:4px;">{wacc_badge}</div>',
                unsafe_allow_html=True,
            )
        with h2:
            if st.button("Save", key=f"save_assumptions_{ticker}",
                         use_container_width=True,
                         help="Persist these assumptions for this ticker."):
                if on_save is not None:
                    on_save(current)
                    st.toast(f"Assumptions saved for {ticker}.", icon="💾")
        with h3:
            if st.button("Reset", key=f"reset_assumptions_{ticker}",
                         use_container_width=True,
                         help="Discard custom edits and reload the base case."):
                st.session_state[f"assumptions_{ticker}_user"] = base.to_dict()
                st.session_state[preset_key] = "Base case"
                if on_reset is not None:
                    on_reset()
                st.rerun()

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # ---- Three columns: WACC | Capital | Projection ----
        col_w, col_c, col_p = st.columns(3)

        # ---- WACC components ----
        with col_w:
            st.markdown(
                '<div class="eq-section-label" '
                'style="color:var(--accent); margin-bottom:6px;">'
                'WACC COMPONENTS</div>', unsafe_allow_html=True,
            )
            new_beta = st.number_input(
                _label("Beta", modified="beta" in diff),
                value=float(current.beta), step=0.05, format="%.2f",
                help="Equity beta — sensitivity to the broad market. "
                     "Default comes from a 5y monthly OLS regression vs S&P 500.",
                key=f"beta_{ticker}",
            )
            new_rf = st.number_input(
                _label("Risk-free rate", modified="risk_free" in diff),
                value=float(current.risk_free), step=0.0025, format="%.4f",
                help="Default: 10Y US Treasury yield (FRED).",
                key=f"rf_{ticker}",
            )
            new_erp = st.number_input(
                _label("Equity risk premium", modified="equity_risk_premium" in diff),
                value=float(current.equity_risk_premium), step=0.0025, format="%.4f",
                help="Default: Damodaran ERP USA (5.5%).",
                key=f"erp_{ticker}",
            )
            new_cod = st.number_input(
                _label("Cost of debt (pre-tax)", modified="cost_of_debt" in diff),
                value=float(current.cost_of_debt), step=0.0025, format="%.4f",
                help="Default: interest expense / average total debt over 3 years.",
                key=f"cod_{ticker}",
            )
            new_tax = st.number_input(
                _label("Tax rate", modified="tax_rate" in diff),
                value=float(current.tax_rate),
                min_value=0.0, max_value=0.60, step=0.01, format="%.4f",
                help="Default: 3-year average effective tax rate from the income statement.",
                key=f"tax_{ticker}",
            )

        # ---- Capital structure ----
        with col_c:
            st.markdown(
                '<div class="eq-section-label" '
                'style="color:var(--accent); margin-bottom:6px;">'
                'CAPITAL STRUCTURE</div>', unsafe_allow_html=True,
            )
            new_we = st.number_input(
                _label("Equity %", modified="weight_equity" in diff),
                value=float(current.weight_equity * 100),
                min_value=1.0, max_value=99.0, step=1.0, format="%.1f",
                help="Equity share of capital — default uses market cap / "
                     "(market cap + total debt). Falls back to book equity "
                     "when no market cap is available.",
                key=f"we_{ticker}",
            ) / 100.0
            st.markdown(
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:6px; letter-spacing:0.4px;">'
                f'DEBT  <b style="color:var(--text-primary);">'
                f'{(1.0 - new_we) * 100:.1f}%</b></div>',
                unsafe_allow_html=True,
            )
            render_capital_structure_bar(weight_equity=new_we)

        # ---- Projection ----
        with col_p:
            st.markdown(
                '<div class="eq-section-label" '
                'style="color:var(--accent); margin-bottom:6px;">'
                'PROJECTION</div>', unsafe_allow_html=True,
            )
            new_s1 = int(st.number_input(
                _label("High-growth period (years)", modified="stage1_years" in diff),
                value=int(current.stage1_years),
                min_value=2, max_value=10, step=1,
                help="Stage 1 of the DCF — explicit high-growth period.",
                key=f"s1_{ticker}",
            ))
            new_s2 = int(st.number_input(
                _label("Fade period (years)", modified="stage2_years" in diff),
                value=int(current.stage2_years),
                min_value=0, max_value=10, step=1,
                help="Stage 2 — linear/logistic fade toward terminal growth.",
                key=f"s2_{ticker}",
            ))
            new_g_t = st.number_input(
                _label("Terminal growth", modified="terminal_growth" in diff),
                value=float(current.terminal_growth),
                step=0.0025, format="%.4f",
                help="Long-run growth in perpetuity — should be near long-term "
                     "inflation (2–3%).",
                key=f"gt_{ticker}",
            )
            new_g1 = st.number_input(
                _label("Override growth (0 = historical CAGR)",
                       modified="override_growth" in diff),
                value=float(current.override_growth),
                step=0.01, format="%.4f",
                help="Force a stage-1 growth rate. 0 means use the realised "
                     "5y FCF CAGR (clipped to ±30%).",
                key=f"gov_{ticker}",
            )

        # ---- Monte Carlo subsection ----
        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label" '
            'style="color:var(--accent); margin-bottom:8px;">'
            'MONTE CARLO INPUTS</div>', unsafe_allow_html=True,
        )
        st.caption(
            "These parameters control the probability distributions used in "
            "the DCF Monte Carlo. Defaults are derived from the company's "
            "historical revenue growth dispersion."
        )
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            new_n = int(st.slider(
                _label("Simulations", modified="mc_n_simulations" in diff),
                min_value=500, max_value=20_000,
                value=int(current.mc_n_simulations), step=500,
                help="More sims = smoother distribution but slower (10k ≈ 8s).",
                key=f"mcn_{ticker}",
            ))
        with m2:
            new_revstd = st.number_input(
                _label("Revenue growth std", modified="mc_rev_growth_std" in diff),
                value=float(current.mc_rev_growth_std),
                step=0.005, format="%.4f",
                help="Std of the random stage-1 growth draws.",
                key=f"mcrs_{ticker}",
            )
        with m3:
            new_wstd = st.number_input(
                _label("WACC std", modified="mc_wacc_std" in diff),
                value=float(current.mc_wacc_std),
                step=0.0025, format="%.4f",
                help="Std of the random WACC draws (50bp default).",
                key=f"mcws_{ticker}",
            )
        with m4:
            band = st.slider(
                _label(
                    "Terminal growth band",
                    modified=("mc_terminal_low" in diff
                              or "mc_terminal_high" in diff),
                ),
                min_value=0.0, max_value=0.06,
                value=(float(current.mc_terminal_low),
                       float(current.mc_terminal_high)),
                step=0.0025, format="%.3f",
                help="Uniform sampling band for the terminal growth rate.",
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
        override_growth=float(new_g1),
        mc_n_simulations=int(new_n),
        mc_rev_growth_std=float(new_revstd),
        mc_wacc_std=float(new_wstd),
        mc_terminal_low=float(new_t_low),
        mc_terminal_high=float(new_t_high),
    )

    _persist(ticker, updated)

    # If the user actually edited something while a non-Custom preset was
    # active, flip the selector to Custom on the NEXT rerun.
    new_diff = modified_fields(updated, apply_preset(base, preset))
    if new_diff and preset != "Custom":
        force_custom(preset_key)

    return updated
