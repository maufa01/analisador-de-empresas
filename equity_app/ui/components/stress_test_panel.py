"""
Stress-test sub-tabs for the Valuation tab — rates / USD / recession /
sector shocks. Each sub-tab renders a base-vs-stressed table plus a
horizontal bar chart of % change in intrinsic.

Reads from the four ``analysis.stress_testing.*Result`` dataclasses; the
caller supplies them already-computed.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.stress_testing import (
    RatesShockResult, USDShockResult, RecessionResult, SectorShockResult,
)
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, GAINS,
)


# Same muted-copper used in peer ranking for downside cells —
# rules out the bright-orange Material-Design vibe.
_DOWNSIDE = "rgba(184,115,51,1)"


# ============================================================
# Shared helpers
# ============================================================
def _change_color(pct: float) -> str:
    return GAINS if pct >= 0 else _DOWNSIDE


def _bar_chart(
    *, x: list[str], y: list[float], labels: list[str], height: int = 280,
) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=x, y=y,
        marker=dict(color=[_change_color(v) for v in y]),
        text=labels, textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, type="category"),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, ticksuffix="%",
                   title="Δ intrinsic"),
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY)),
    )
    return fig


def _empty(msg: str) -> None:
    st.markdown(
        '<div class="eq-card" style="padding:18px; color:var(--text-muted); '
        f'font-size:13px;">{msg}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# A — Rates shock
# ============================================================
def _render_rates(res: Optional[RatesShockResult]) -> None:
    if res is None or not res.scenarios:
        _empty("Rates shock could not be computed (DCF unavailable for this ticker).")
        return

    st.markdown(
        '<div class="eq-card" style="padding:14px 18px; margin-bottom:10px;">'
        f'<span style="color:var(--text-muted); font-size:12px;">Base intrinsic </span>'
        f'<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">${res.base_intrinsic:,.2f}</span>'
        f'<span style="color:var(--text-muted); font-size:12px; margin:0 10px;">·</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">Base WACC </span>'
        f'<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{res.base_wacc*100:.2f}%</span>'
        + (f'<span style="color:var(--text-muted); font-size:12px; margin:0 10px;">·</span>'
           f'<span style="color:var(--text-muted); font-size:12px;">Current price </span>'
           f'<span style="color:var(--text-primary); font-weight:500; '
           f'font-variant-numeric:tabular-nums;">${res.current_price:,.2f}</span>'
           if res.current_price else "")
        + '</div>',
        unsafe_allow_html=True,
    )

    # Duration interpretation
    if res.modified_duration is not None:
        st.markdown(
            '<div class="eq-card" style="padding:12px 16px; '
            'border-left:3px solid var(--accent); margin-bottom:12px;">'
            f'<span class="eq-idx-label">MODIFIED DURATION · '
            f'{res.modified_duration:.1f}</span>'
            f'<div style="color:var(--text-secondary); font-size:13px; '
            f'margin-top:4px;">{res.interpretation}</div></div>',
            unsafe_allow_html=True,
        )

    # Table
    rows = ""
    for s in res.scenarios:
        change_color = _change_color(s.change_from_base_pct)
        rows += (
            "<tr>"
            f"<td style='padding:10px 14px; color:var(--text-primary); "
            f"border-bottom:1px solid var(--border);'>+{s.shock_bps} bps</td>"
            f"<td style='padding:10px 14px; text-align:right; "
            f"color:var(--text-secondary); font-variant-numeric:tabular-nums; "
            f"border-bottom:1px solid var(--border);'>{s.new_risk_free*100:.2f}%</td>"
            f"<td style='padding:10px 14px; text-align:right; "
            f"color:var(--text-primary); font-variant-numeric:tabular-nums; "
            f"border-bottom:1px solid var(--border);'>{s.new_wacc*100:.2f}%</td>"
            f"<td style='padding:10px 14px; text-align:right; "
            f"color:var(--text-primary); font-weight:500; "
            f"font-variant-numeric:tabular-nums; "
            f"border-bottom:1px solid var(--border);'>${s.intrinsic:,.2f}</td>"
            f"<td style='padding:10px 14px; text-align:right; color:{change_color}; "
            f"font-variant-numeric:tabular-nums; "
            f"border-bottom:1px solid var(--border);'>"
            f"{s.change_from_base_pct:+.1f}%</td>"
            "</tr>"
        )

    st.markdown(
        '<div class="eq-card" style="padding:0; overflow:hidden;">'
        '<table style="width:100%; border-collapse:collapse;">'
        '<thead><tr style="background:var(--surface-raised);">'
        '<th style="padding:11px 14px; text-align:left; '
        'color:var(--text-muted); font-size:11px; letter-spacing:0.6px; '
        'text-transform:uppercase;">Shock</th>'
        '<th style="padding:11px 14px; text-align:right; '
        'color:var(--text-muted); font-size:11px; letter-spacing:0.6px; '
        'text-transform:uppercase;">Risk-free</th>'
        '<th style="padding:11px 14px; text-align:right; '
        'color:var(--text-muted); font-size:11px; letter-spacing:0.6px; '
        'text-transform:uppercase;">WACC</th>'
        '<th style="padding:11px 14px; text-align:right; '
        'color:var(--text-muted); font-size:11px; letter-spacing:0.6px; '
        'text-transform:uppercase;">Intrinsic</th>'
        '<th style="padding:11px 14px; text-align:right; '
        'color:var(--text-muted); font-size:11px; letter-spacing:0.6px; '
        'text-transform:uppercase;">Change</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )

    # Bar chart
    fig = _bar_chart(
        x=[f"+{s.shock_bps}bps" for s in res.scenarios],
        y=[s.change_from_base_pct for s in res.scenarios],
        labels=[f"${s.intrinsic:,.0f}" for s in res.scenarios],
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ============================================================
# B — USD shock
# ============================================================
def _render_usd(res: USDShockResult) -> None:
    if not res.applicable:
        _empty(
            f"USD shock not applicable — {res.note} "
            f"(international revenue est. {(res.international_pct or 0)*100:.0f}%)."
        )
        return
    if not res.scenarios:
        _empty("USD shock could not be computed.")
        return

    st.markdown(
        '<div class="eq-card" style="padding:14px 18px; margin-bottom:10px;">'
        f'<span style="color:var(--text-muted); font-size:12px;">Base intrinsic </span>'
        f'<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">${res.base_intrinsic:,.2f}</span>'
        f'<span style="color:var(--text-muted); font-size:12px; margin:0 10px;">·</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'Est. international revenue </span>'
        f'<span style="color:var(--accent); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">'
        f'{res.international_pct*100:.0f}%</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    fig = _bar_chart(
        x=[s.name for s in res.scenarios],
        y=[s.change_pct for s in res.scenarios],
        labels=[f"${s.intrinsic:,.0f}" for s in res.scenarios],
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(res.note)


# ============================================================
# C — Recession scenarios
# ============================================================
def _render_recession(res: Optional[RecessionResult]) -> None:
    if res is None or not res.scenarios:
        _empty("Recession scenarios could not be computed.")
        return

    st.markdown(
        '<div style="color:var(--text-muted); font-size:12px; '
        'margin-bottom:12px;">Base intrinsic '
        '<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">${res.base_intrinsic:,.2f}</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(res.scenarios), gap="small")
    for col, s in zip(cols, res.scenarios):
        change_color = _change_color(s.change_pct)
        with col:
            st.markdown(
                '<div class="eq-card" style="padding:14px 16px; '
                f'border-left:3px solid {change_color}; min-height:140px;">'
                '<div class="eq-idx-label" style="font-size:10px;">'
                f'{s.scenario_name.upper()}</div>'
                f'<div style="color:var(--text-primary); font-size:22px; '
                f'font-weight:500; letter-spacing:-0.4px; '
                f'font-variant-numeric:tabular-nums; margin-top:6px;">'
                f'${s.intrinsic:,.2f}</div>'
                f'<div style="color:{change_color}; font-size:13px; '
                f'font-variant-numeric:tabular-nums; margin-top:2px;">'
                f'{s.change_pct:+.1f}%</div>'
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:8px;">Duration: {s.duration_months}m</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    with st.expander("Show shock parameters", expanded=False):
        df = pd.DataFrame([{
            "Scenario": s.scenario_name,
            "Revenue Δ Y1": f"{s.revenue_decline_yr1*100:+.0f}%",
            "Margin Δ": f"{s.margin_compression*100:+.0f}pp",
            "WACC shock": f"+{s.wacc_shock*100:.1f}pp",
            "Duration": f"{s.duration_months} months",
        } for s in res.scenarios])
        st.dataframe(df, hide_index=True, use_container_width=True)


# ============================================================
# D — Sector shocks
# ============================================================
def _render_sector(res: SectorShockResult) -> None:
    if not res.applicable or not res.scenarios:
        _empty(res.note)
        return

    st.markdown(
        '<div style="color:var(--text-muted); font-size:12px; '
        'margin-bottom:12px;">'
        f'Sector: <span style="color:var(--accent); font-weight:500;">'
        f'{res.sector}</span>'
        '<span style="margin:0 10px;">·</span>Base intrinsic '
        '<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">${res.base_intrinsic:,.2f}</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    fig = _bar_chart(
        x=[s.name for s in res.scenarios],
        y=[s.change_pct for s in res.scenarios],
        labels=[f"${s.intrinsic:,.0f}" for s in res.scenarios],
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(res.note)


# ============================================================
# Public API
# ============================================================
def render_stress_test_panel(
    *,
    rates: Optional[RatesShockResult],
    usd: USDShockResult,
    recession: Optional[RecessionResult],
    sector: SectorShockResult,
) -> None:
    """Render four stress-test sub-tabs."""
    st.markdown(
        '<div class="eq-section-label" style="margin-top:8px;">'
        'STRESS TESTING · SCENARIO ANALYSIS</div>',
        unsafe_allow_html=True,
    )
    t1, t2, t3, t4 = st.tabs([
        "Rates shock", "USD strength", "Recession", "Sector-specific",
    ])
    with t1: _render_rates(rates)
    with t2: _render_usd(usd)
    with t3: _render_recession(recession)
    with t4: _render_sector(sector)
