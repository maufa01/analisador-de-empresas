"""
Reverse-DCF UI section — runs the solver and renders three artefacts:
- Big metric: the implied stage-1 growth, framed against historical
  and (optional) industry growth.
- Visual comparison bars (target vs historical vs industry).
- Plain-English interpretation card with the verdict.

All HTML emitted as single-line, no-leading-whitespace strings to
avoid Streamlit's markdown indented-code-block trap.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from valuation.reverse_dcf import ReverseDCFResult


def _bar_html(label: str, value: Optional[float], scale_max: float, color: str) -> str:
    if value is None:
        text = "—"
        fill = 0.0
    else:
        text = f"{value * 100:+.2f}%"
        fill = min(max(value / scale_max * 100.0, 0.0), 100.0) if scale_max > 0 else 0.0
    return (
        '<div style="margin-bottom:8px;">'
        '<div style="display:flex; justify-content:space-between; '
        'margin-bottom:3px;">'
        f'<span style="color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.4px;">{label.upper()}</span>'
        f'<span style="color:var(--text-primary); font-size:13px; '
        f'font-variant-numeric:tabular-nums; font-weight:500;">{text}</span>'
        '</div>'
        '<div style="background:var(--surface-raised); height:5px; '
        'border-radius:3px; overflow:hidden;">'
        f'<div style="background:{color}; width:{fill}%; height:100%;"></div>'
        '</div>'
        '</div>'
    )


def render_reverse_dcf_section(result: ReverseDCFResult) -> None:
    """Render the full reverse-DCF block."""
    if result.implied_growth is None:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'⚠ {result.error or "Reverse DCF could not solve."}'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    implied = result.implied_growth
    historical = result.historical_growth
    industry = result.industry_growth

    # Big headline + assumption summary
    headline_color = (
        "var(--gains)"
        if (historical is not None and historical > 0
            and 0.5 <= implied / max(historical, 1e-6) <= 2.0)
        else "var(--accent)"
    )
    if implied < 0:
        headline_color = "var(--losses)"

    st.markdown(
        '<div class="eq-card" style="padding:18px 22px;">'
        '<div class="eq-idx-label">MARKET-IMPLIED EXPECTATIONS</div>'
        f'<div style="font-size:32px; font-weight:500; '
        f'letter-spacing:-0.5px; color:{headline_color}; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{implied * 100:+.2f}% / yr</div>'
        '<div style="color:var(--text-secondary); font-size:13px; '
        'margin-top:6px;">'
        f'Stage-1 revenue growth implied by the market price of '
        f'<b style="color:var(--text-primary); '
        f'font-variant-numeric:tabular-nums;">${result.target_price:,.2f}</b>'
        f' under WACC '
        f'<b style="color:var(--text-primary);">{result.wacc:.2%}</b> '
        f'and terminal growth '
        f'<b style="color:var(--text-primary);">{result.terminal_growth:.2%}</b>.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Comparison bars
    scale_max = max(
        abs(implied), abs(historical or 0.0), abs(industry or 0.0), 0.01,
    )
    bars = (
        _bar_html("Implied (market)", implied,         scale_max,
                  "rgba(201,169,97,0.85)") +
        _bar_html("Historical 5y CAGR", historical,    scale_max,
                  "rgba(16,185,129,0.85)") +
        _bar_html("Industry average",   industry,      scale_max,
                  "rgba(156,163,175,0.6)")
    )
    st.markdown(
        '<div class="eq-card" style="padding:18px;">'
        '<div class="eq-idx-label" style="margin-bottom:12px;">'
        'GROWTH COMPARISON</div>'
        + bars +
        '</div>',
        unsafe_allow_html=True,
    )

    # Interpretation
    if result.interpretation:
        st.markdown(
            '<div class="eq-card" '
            'style="padding:16px 18px; border-left:3px solid var(--accent);">'
            '<div class="eq-idx-label" style="margin-bottom:6px;">'
            'INTERPRETATION</div>'
            f'<div style="color:var(--text-secondary); font-size:13px; '
            f'line-height:1.55;">{result.interpretation}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
