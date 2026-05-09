"""
Market-implied growth header card.

Solves the question: "what stage-1 growth rate does the market need
the company to deliver to JUSTIFY today's price?"

Computed via :func:`valuation.reverse_dcf.run_reverse_dcf`. The card
renders three pieces:

1. The implied growth (e.g. "Market is pricing 14.5% growth").
2. The historical 5-year revenue CAGR for context.
3. A verdict line based on the gap (cheap / fair / rich).

Fails silently and renders nothing for tickers where the FCFF DCF
doesn't apply (banks, insurers, REITs — caught by the
:mod:`analysis.industry_classifier` short-circuit upstream).
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st


def _historical_rev_cagr(income: pd.DataFrame, periods: int = 5) -> Optional[float]:
    if "revenue" not in income.columns:
        return None
    s = income["revenue"].dropna()
    if len(s) < periods + 1 or s.iloc[-periods - 1] <= 0:
        return None
    return float((s.iloc[-1] / s.iloc[-periods - 1]) ** (1.0 / periods) - 1.0)


def _verdict(implied: float, historical: Optional[float]) -> tuple[str, str]:
    """(verdict_text, color_var). Heuristic gap thresholds."""
    if historical is None:
        return ("Hard to judge — no historical CAGR available.",
                "var(--accent)")
    gap = implied - historical
    if gap > 0.05:
        return (f"Market is pricing **{gap*100:+.1f} pp** above historical — "
                f"richly valued unless growth is set to accelerate.",
                "var(--losses)")
    if gap > 0.02:
        return (f"Market is pricing **{gap*100:+.1f} pp** above historical — "
                "fair-to-rich; needs the trend to continue.",
                "rgba(184,115,51,1)")
    if gap > -0.02:
        return ("**In line** with historical CAGR — fairly valued on this metric.",
                "var(--accent)")
    if gap > -0.05:
        return (f"Market is pricing **{gap*100:+.1f} pp** below historical — "
                "fair-to-cheap; possible mispricing or expected slowdown.",
                "var(--gains)")
    return (f"Market is pricing **{gap*100:+.1f} pp** below historical — "
            "deeply discounted (or the historical pace is unsustainable).",
            "var(--gains)")


def render_market_implied_growth_card(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    current_price: Optional[float],
    wacc: Optional[float],
    terminal_growth: Optional[float] = None,
    stage1_years: Optional[int] = None,
    stage2_years: Optional[int] = None,
) -> Optional[float]:
    """Render the card. Returns the implied stage-1 growth (decimal),
    or ``None`` when the reverse DCF couldn't solve — useful for the
    snapshot DB to record."""
    if (current_price is None or current_price <= 0
            or wacc is None or income is None or income.empty):
        return None
    try:
        from valuation.reverse_dcf import run_reverse_dcf
        result = run_reverse_dcf(
            income=income, balance=balance, cash=cash,
            target_price=float(current_price),
            wacc=float(wacc),
            terminal_growth=terminal_growth,
            stage1_years=stage1_years,
            stage2_years=stage2_years,
        )
    except Exception:
        return None

    if result is None or result.implied_growth is None:
        return None
    if not np.isfinite(result.implied_growth):
        return None

    implied = float(result.implied_growth)
    historical = _historical_rev_cagr(income, periods=5)
    verdict_text, color = _verdict(implied, historical)

    hist_html = (
        f'<span style="color:var(--text-muted); margin-left:18px;">'
        f'5y historical CAGR: '
        f'<b style="color:var(--text-secondary); '
        f'font-variant-numeric:tabular-nums;">{historical*100:+.2f}%</b></span>'
        if historical is not None else ""
    )

    st.markdown(
        '<div style="background:var(--surface); border-left:3px solid '
        f'{color}; padding:14px 18px; border-radius:6px; '
        'margin-bottom:6px;">'
        '<div style="color:var(--text-muted); font-size:11px; '
        'text-transform:uppercase; letter-spacing:0.6px;">'
        'Market-implied stage-1 growth</div>'
        '<div style="display:flex; align-items:baseline; '
        'gap:0; margin-top:4px; flex-wrap:wrap;">'
        f'<span style="color:var(--text-primary); font-size:24px; '
        f'font-weight:600; font-variant-numeric:tabular-nums;">'
        f'{implied*100:+.2f}%</span>'
        f'{hist_html}</div>'
        f'<div style="color:var(--text-secondary); font-size:12px; '
        f'margin-top:8px; line-height:1.4;">{verdict_text}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    return implied
