"""
Returns row — mini-cards per period (1D / 1W / 1M / 3M / YTD / 1Y / 3Y / 5Y / 10Y)
plus optional benchmark-comparison rows underneath.

All HTML emitted as single-line, no-leading-whitespace strings to avoid
Streamlit's markdown indented-code-block trap.
"""
from __future__ import annotations
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st


# ============================================================
# Period math
# ============================================================
def _ret_for_period(prices: pd.Series, days_back: int) -> Optional[float]:
    """Return (last / past − 1) × 100 over the latest ``days_back`` calendar days."""
    if prices is None or prices.empty:
        return None
    s = prices.dropna()
    if len(s) < 2:
        return None
    last_dt = s.index[-1]
    target_dt = last_dt - pd.Timedelta(days=days_back)
    past = s[s.index <= target_dt]
    if past.empty:
        return None
    last = float(s.iloc[-1])
    prev = float(past.iloc[-1])
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _ret_ytd(prices: pd.Series) -> Optional[float]:
    """Year-to-date return."""
    if prices is None or prices.empty:
        return None
    s = prices.dropna()
    if s.empty:
        return None
    last = s.iloc[-1]
    last_dt = s.index[-1]
    yr_start = pd.Timestamp(year=last_dt.year, month=1, day=1)
    past = s[s.index >= yr_start]
    if past.empty:
        return None
    first = float(past.iloc[0])
    if first == 0:
        return None
    return (float(last) / first - 1.0) * 100.0


# 1W ≈ 7 calendar days, 1M ≈ 30, 3M ≈ 91, 1Y = 365, etc.
_PERIODS: list[tuple[str, Optional[int]]] = [
    ("1D",  1),
    ("1W",  7),
    ("1M",  30),
    ("3M",  91),
    ("YTD", None),                # special: handled separately
    ("1Y",  365),
    ("3Y",  365 * 3),
    ("5Y",  365 * 5),
    ("10Y", 365 * 10),
]


def compute_returns(prices: pd.Series) -> dict[str, Optional[float]]:
    """Compute all returns for a single price series. None where insufficient history."""
    out: dict[str, Optional[float]] = {}
    for label, days in _PERIODS:
        if label == "YTD":
            out[label] = _ret_ytd(prices)
        else:
            out[label] = _ret_for_period(prices, days) if days is not None else None
    return out


# ============================================================
# Render — single st.markdown call so the eq-card wrapper sticks
# ============================================================
def _ret_cell(label: str, value: Optional[float]) -> str:
    if value is None:
        body = '<span style="color:var(--text-muted);">—</span>'
    else:
        sign = "+" if value >= 0 else ""
        color = "var(--gains)" if value >= 0 else "var(--losses)"
        body = (
            f'<span style="color:{color}; font-weight:500; '
            f'font-variant-numeric:tabular-nums; font-size:14px;">'
            f'{sign}{value:.2f}%</span>'
        )
    return (
        '<div style="display:flex; flex-direction:column; align-items:center; '
        'padding:6px 4px; flex:1; min-width:55px;">'
        f'<div style="color:var(--text-muted); font-size:10px; '
        f'letter-spacing:0.6px; text-transform:uppercase;">{label}</div>'
        f'<div style="margin-top:4px;">{body}</div>'
        '</div>'
    )


def render_returns_row(returns: dict[str, Optional[float]]) -> None:
    """Render a single horizontal row of period mini-cards."""
    cells = "".join(_ret_cell(p, returns.get(p)) for p, _ in _PERIODS)
    html = (
        '<div class="eq-card" style="padding:8px 12px;">'
        '<div style="display:flex; flex-wrap:wrap; gap:0;">'
        + cells +
        '</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_benchmark_comparison(
    *,
    target: Optional[float],
    benchmark: Optional[float],
    label: str,
) -> str:
    """
    Returns a single-line HTML span comparing target vs benchmark.
    Caller can stitch several into one row.
    """
    if target is None or benchmark is None:
        return (
            f'<span style="color:var(--text-muted); font-size:12px;">'
            f'vs {label}: —</span>'
        )
    diff = target - benchmark
    sign = "+" if diff >= 0 else ""
    color = "var(--gains)" if diff >= 0 else "var(--losses)"
    word = "outperform" if diff >= 0 else "underperform"
    return (
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'vs <b style="color:var(--text-secondary);">{label}</b> · '
        f'<span style="color:{color};">{word} {sign}{diff:.2f}%</span></span>'
    )


def render_benchmark_row(comparisons: list[str]) -> None:
    """Render a single line of benchmark comparison spans."""
    if not comparisons:
        return
    body = ' &nbsp; · &nbsp; '.join(comparisons)
    st.markdown(
        f'<div style="padding:6px 14px; margin-top:4px;">{body}</div>',
        unsafe_allow_html=True,
    )
