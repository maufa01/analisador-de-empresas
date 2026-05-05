"""
Quick-metrics row using native ``st.metric`` (no custom HTML).

The previous implementation built each card via ``st.markdown(html,
unsafe_allow_html=True)`` and broke when newer Streamlit releases
tightened HTML escaping — closing ``</div>`` tags rendered as literal
text. ``st.metric`` is native and styled by the global theme rules in
``ui/theme.py``.
"""
from __future__ import annotations
from typing import Optional, Sequence

import streamlit as st


def _fmt_money_short(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e12: return f"${v/1e12:,.2f}T"
    if av >= 1e9:  return f"${v/1e9:,.2f}B"
    if av >= 1e6:  return f"${v/1e6:,.1f}M"
    if av >= 1e3:  return f"${v/1e3:,.1f}K"
    return f"${v:,.2f}"


def _fmt_pct(v: Optional[float], *, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}%"


def render_quick_metrics(
    *,
    revenue: Optional[float],
    net_margin_pct: Optional[float],
    roic_pct: Optional[float],
    eq_flag: Optional[str],
    revenue_yoy_pct: Optional[float] = None,
) -> None:
    """
    Render 4 native ``st.metric`` cards in a single row.

    Args:
        revenue:          latest revenue in USD (will be shown short).
        net_margin_pct:   already in % units (e.g. 25.3 not 0.253).
        roic_pct:         same.
        eq_flag:          "GREEN" | "YELLOW" | "RED" | "UNKNOWN".
        revenue_yoy_pct:  optional YoY revenue growth in % units.
    """
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="REVENUE (LATEST)",
            value=_fmt_money_short(revenue),
            delta=(f"{revenue_yoy_pct:+.2f}% YoY"
                   if revenue_yoy_pct is not None else None),
        )
    with c2:
        st.metric(
            label="NET MARGIN",
            value=_fmt_pct(net_margin_pct),
        )
    with c3:
        st.metric(
            label="ROIC",
            value=_fmt_pct(roic_pct),
        )
    with c4:
        st.metric(
            label="EARNINGS QUALITY",
            value=(eq_flag or "—").upper(),
        )


def render_metric_row(items: Sequence[dict]) -> None:
    """
    Generic row of ``st.metric`` cards. Each ``items`` entry is a dict
    forwarded as kwargs (label, value, delta, help, ...).
    """
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            st.metric(**item)
