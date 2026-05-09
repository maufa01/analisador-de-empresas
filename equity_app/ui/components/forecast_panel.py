"""
Forecast tab — 5-year projection of statements + cash generation.

Single-scenario view shows headline FCF metrics + an annual/cumulative
FCF chart + the projected income & cash-flow statements rendered by
:func:`render_income_statement` / :func:`render_cash_flow` in hybrid
mode. Compare-all view overlays bull / base / bear cumulative FCF with
a side-by-side parameter table.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.financial_forecast import (
    ForecastInputs, ForecastResult,
    _default_inputs_from_history,
    project_bull_bear_base,
)
from ui.components.financial_table import (
    render_income_statement, render_cash_flow,
)
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"
_SCENARIO_COLOURS = {"bull": GAINS, "base": TEXT_SECONDARY, "bear": _DOWNSIDE}


# ============================================================
# Public entry
# ============================================================
def render_forecast_panel(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    shares_outstanding: float | None = None,
    current_price: float | None = None,
) -> None:
    """5-year projection of statements + cash generation."""
    if income is None or income.empty:
        st.info("Forecast needs an income statement.")
        return

    st.markdown(
        '<div class="eq-section-label">5-YEAR FINANCIAL FORECAST</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Future statements projected from historical defaults. Toggle "
        "scenarios to test bull / bear sensitivity."
    )

    c1, c2, c3 = st.columns([1.2, 2, 1.2])
    with c1:
        years = int(st.select_slider(
            "Years forward", options=[3, 5, 6, 10], value=5,
            key="fc_years",
        ))
    with c2:
        scenario = st.radio(
            "Scenario",
            ["Base", "Bull", "Bear", "Compare all"],
            horizontal=True, label_visibility="collapsed",
            key="fc_scenario",
        )
    with c3:
        show_assumptions = st.checkbox(
            "Assumptions detail", value=False, key="fc_show_assump",
        )

    base_inputs = _default_inputs_from_history(income, balance, cash, years)
    scenarios = project_bull_bear_base(income, balance, cash, base_inputs, years)

    if scenario == "Compare all":
        _render_scenario_comparison(scenarios, current_price)
    else:
        result = scenarios[scenario.lower()]
        _render_single_scenario(result, shares_outstanding, current_price, scenario.lower())

    if show_assumptions:
        _render_assumptions_detail(base_inputs)


# ============================================================
# Single-scenario view
# ============================================================
def _render_single_scenario(
    result: ForecastResult,
    shares_outstanding: float | None,
    current_price: float | None,
    scenario_name: str,
) -> None:
    fcff = result.fcff_per_year
    if fcff is None or fcff.empty:
        st.warning(
            "Forecast has no FCF series — historical OCF margin and "
            "capex %-of-revenue are missing. Provide an inputs override."
        )
        return

    cum = result.cumulative_fcf.iloc[-1]
    avg = float(fcff.mean())
    span = len(fcff)

    cards = st.columns(3)
    with cards[0]:
        st.markdown(_metric_card(
            f"Cumulative FCF ({span}y)",
            _money(cum),
            f"{scenario_name.title()} scenario",
            color=ACCENT,
        ), unsafe_allow_html=True)
    with cards[1]:
        st.markdown(_metric_card(
            "Avg annual FCF", _money(avg), "", color=TEXT_SECONDARY,
        ), unsafe_allow_html=True)
    with cards[2]:
        if shares_outstanding and shares_outstanding > 0:
            cum_per_share = cum / shares_outstanding
            sub = (f"vs current price ${current_price:,.2f}"
                   if current_price else "")
            st.markdown(_metric_card(
                f"Cumulative FCF / share ({span}y)",
                f"${cum_per_share:,.2f}", sub,
                color=GAINS,
            ), unsafe_allow_html=True)
        else:
            st.markdown(_metric_card(
                "Cumulative FCF / share", "—",
                "shares outstanding unavailable",
                color=TEXT_SECONDARY,
            ), unsafe_allow_html=True)

    # FCF chart
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">PROJECTED FREE CASH FLOW</div>',
        unsafe_allow_html=True,
    )
    fig = go.Figure()
    years_axis = [
        d.year if isinstance(d, pd.Timestamp) else int(d)
        for d in fcff.index
    ]
    fig.add_trace(go.Bar(
        x=years_axis,
        y=(fcff.values / 1e9),
        marker_color=TEXT_SECONDARY,
        name="FCF",
        text=[f"${v/1e9:.1f}B" for v in fcff.values],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        x=years_axis,
        y=(result.cumulative_fcf.values / 1e9),
        line=dict(color=ACCENT, width=2),
        marker=dict(size=8),
        name="Cumulative",
        yaxis="y2",
        mode="lines+markers",
    ))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        yaxis=dict(title="Annual FCF ($B)", gridcolor=BORDER, color=TEXT_MUTED),
        yaxis2=dict(title="Cumulative ($B)", overlaying="y", side="right",
                    gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # Projected statements via the hybrid renderer (no CAGR for projection)
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">PROJECTED INCOME STATEMENT</div>',
        unsafe_allow_html=True,
    )
    render_income_statement(
        result.income_projected, view="hybrid",
        show_ttm=False, show_cagr=False,
    )

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">PROJECTED CASH FLOW</div>',
        unsafe_allow_html=True,
    )
    render_cash_flow(
        result.cash_flow_projected, view="hybrid",
        show_ttm=False, show_cagr=False,
    )


# ============================================================
# Compare all
# ============================================================
def _render_scenario_comparison(
    scenarios: dict[str, ForecastResult],
    current_price: float | None,
) -> None:
    fig = go.Figure()
    for name, result in scenarios.items():
        cum = result.cumulative_fcf
        if cum is None or cum.empty:
            continue
        years_axis = [
            d.year if isinstance(d, pd.Timestamp) else int(d)
            for d in cum.index
        ]
        fig.add_trace(go.Scatter(
            x=years_axis, y=(cum.values / 1e9),
            line=dict(color=_SCENARIO_COLOURS.get(name, TEXT_SECONDARY), width=2),
            marker=dict(size=8),
            name=name.title(),
            mode="lines+markers",
        ))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        title=dict(text="Cumulative FCF · Bull / Base / Bear",
                   font=dict(color=TEXT_PRIMARY, size=14)),
        yaxis=dict(title="Cumulative FCF ($B)", gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # Side-by-side parameter table
    rows: list[dict] = []
    for name in ("bull", "base", "bear"):
        result = scenarios.get(name)
        if result is None:
            continue
        inp = result.inputs_used
        op_path = inp.operating_margin_path or []
        avg_op = (sum(op_path) / len(op_path)) if op_path else None
        row = {
            "Scenario": name.title(),
            "Y1 Rev growth": (
                f"{inp.revenue_growth_path[0]*100:+.1f}%"
                if inp.revenue_growth_path else "—"
            ),
            "Avg Op Margin": (
                f"{avg_op*100:.1f}%" if avg_op is not None else "—"
            ),
            "Cum FCF": _money(result.cumulative_fcf.iloc[-1]),
            "Final-yr FCF": _money(result.fcff_per_year.iloc[-1]),
        }
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ============================================================
# Assumptions detail
# ============================================================
def _render_assumptions_detail(inputs: ForecastInputs) -> None:
    with st.expander("Assumptions used (base case)"):
        def _pct_path(path):
            return [f"{v*100:.2f}%" for v in path] if path else None
        st.json({
            "revenue_growth_path":   _pct_path(inputs.revenue_growth_path),
            "gross_margin_path":     _pct_path(inputs.gross_margin_path),
            "operating_margin_path": _pct_path(inputs.operating_margin_path),
            "net_margin_path":       _pct_path(inputs.net_margin_path),
            "ebitda_margin_path":    _pct_path(inputs.ebitda_margin_path),
            "ocf_margin": (f"{inputs.ocf_margin*100:.2f}%"
                           if inputs.ocf_margin is not None else None),
            "capex_pct_revenue": (f"{inputs.capex_pct_revenue*100:.2f}%"
                                  if inputs.capex_pct_revenue is not None else None),
            "sbc_pct_revenue": (f"{inputs.sbc_pct_revenue*100:.2f}%"
                                if inputs.sbc_pct_revenue is not None else None),
            "tax_rate": (f"{inputs.tax_rate*100:.2f}%"
                         if inputs.tax_rate is not None else None),
        })


# ============================================================
# Internals
# ============================================================
def _money(v: float) -> str:
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12:
        return f"{sign}${av/1e12:,.2f}T"
    if av >= 1e9:
        return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:
        return f"{sign}${av/1e6:,.1f}M"
    return f"{sign}${av:,.0f}"


def _metric_card(label: str, value: str, sub: str = "",
                 *, color: str = ACCENT) -> str:
    sub_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:11px; '
        f'margin-top:4px;">{sub}</div>' if sub else ""
    )
    return (
        f'<div style="background:{SURFACE}; border:1px solid {BORDER}; '
        f'border-top:3px solid {color}; border-radius:8px; padding:16px;">'
        f'<div style="color:{TEXT_MUTED}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:0.6px;">{label}</div>'
        f'<div style="color:{TEXT_PRIMARY}; font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">{value}</div>'
        f'{sub_html}</div>'
    )
