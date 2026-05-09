"""
Valuation card — model name, intrinsic value, upside/downside vs price.

Used by the Equity Analysis page to summarise each model (DCF, comps,
DDM, RI, MC) in a uniform card. The accent border switches between
gold / emerald / crimson according to upside vs the live price.

The component is markup-only — no business logic. The caller passes
already-computed numbers.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _fmt_range(low: Optional[float], high: Optional[float]) -> str:
    if low is None or high is None:
        return ""
    return f"{_fmt_money(low)} – {_fmt_money(high)}"


def _classify(upside: Optional[float]) -> tuple[str, str]:
    """Returns (css_class_for_text, accent_border_color_var)."""
    if upside is None:
        return "", "var(--border)"
    if upside >= 0.10:
        return "eq-pos", "var(--gains)"
    if upside <= -0.10:
        return "eq-neg", "var(--losses)"
    return "", "var(--accent)"


def render_valuation_card(
    *,
    model: str,
    intrinsic: Optional[float],
    current_price: Optional[float] = None,
    range_low: Optional[float] = None,
    range_high: Optional[float] = None,
    sub_label: Optional[str] = None,
) -> None:
    """
    Render one valuation model summary.

    Args:
        model: short label (e.g. "DCF · 3-stage", "COMPARABLES").
        intrinsic: per-share intrinsic value (the headline number).
        current_price: optional — used to compute upside %.
        range_low / range_high: optional band shown under the headline.
        sub_label: optional context line (e.g. "WACC 9.0% · g 2.5%").
    """
    upside: Optional[float] = None
    if intrinsic is not None and current_price and current_price > 0:
        upside = (intrinsic - current_price) / current_price

    chg_cls, border = _classify(upside)

    upside_html = ""
    if upside is not None:
        sign = "+" if upside >= 0 else ""
        upside_html = (
            f'<span class="eq-idx-change {chg_cls}" style="margin-top:0;">'
            f'{sign}{upside * 100:.1f}% vs ${current_price:,.2f}</span>'
        )

    range_html = ""
    if range_low is not None and range_high is not None:
        range_html = (
            f'<div style="color:var(--text-muted); font-size:11px; '
            f'margin-top:6px; letter-spacing:0.4px;">RANGE  '
            f'{_fmt_range(range_low, range_high)}</div>'
        )

    sub_html = ""
    if sub_label:
        sub_html = (
            f'<div style="color:var(--text-muted); font-size:11px; '
            f'margin-top:4px;">{sub_label}</div>'
        )

    # IMPORTANT: emit the HTML as ONE line with no leading whitespace.
    # Streamlit's markdown parser runs first; any line indented ≥4 spaces
    # becomes a fenced code block and the HTML leaks to the page as
    # literal text — which is the bug the user saw in Image 3.
    html = (
        f'<div class="eq-card" style="border-left:3px solid {border}; '
        f'padding-left:14px;">'
        f'<div class="eq-idx-label">{model}</div>'
        f'<div class="eq-header-metric" style="margin-top:2px;">'
        f'<span class="eq-idx-value">{_fmt_money(intrinsic)}</span>'
        f'{upside_html}</div>'
        f'{range_html}{sub_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
