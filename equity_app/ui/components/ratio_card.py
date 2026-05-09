"""
Single ratio "card" — value + 10y avg + industry benchmark + sparkline.

Used by the Ratios tab to render any of the ~50 metrics we surface
(profitability, efficiency, liquidity, solvency, per-share, valuation).

Layout:
    LABEL (uppercase)
    BIG VALUE (28px, green/red/neutral vs industry avg)
    ────────
    10y avg  ·  Industry avg  ·  Trend arrow
    [sparkline]                       <- st.column_config.AreaChartColumn
                                         doesn't exist standalone, so we
                                         render via st.line_chart with no
                                         axes / no chrome.

All HTML emitted as one ``st.markdown(unsafe_allow_html=True)`` call so
the markdown indented-code-block trap doesn't apply.
"""
from __future__ import annotations
from typing import Literal, Optional, Sequence

import math
import pandas as pd
import streamlit as st

from core.formatters import format_percentage, format_ratio, format_multiple


ValueKind = Literal["pct", "ratio", "multiple", "currency_short", "days"]


def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _fmt_value(v: Optional[float], kind: ValueKind) -> str:
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v:.2f}%"
    if kind == "ratio":
        return f"{v:.2f}"
    if kind == "multiple":
        return f"{v:.2f}x"
    if kind == "days":
        return f"{v:.0f}d"
    if kind == "currency_short":
        if abs(v) >= 1e12: return f"${v / 1e12:,.2f}T"
        if abs(v) >= 1e9:  return f"${v / 1e9:,.2f}B"
        if abs(v) >= 1e6:  return f"${v / 1e6:,.1f}M"
        return f"${v:,.2f}"
    return f"{v:.2f}"


def _color_for_value(
    value: Optional[float],
    industry: Optional[float],
    *,
    higher_better: bool,
) -> str:
    if value is None or industry is None:
        return "var(--text-primary)"
    if higher_better:
        return "var(--gains)" if value >= industry else "var(--losses)"
    return "var(--gains)" if value <= industry else "var(--losses)"


def _trend_arrow(history: Optional[Sequence[float]]) -> str:
    if not history or len(history) < 2:
        return ""
    series = [v for v in history if v is not None]
    if len(series) < 2:
        return ""
    if series[-1] > series[0]:
        return '<span style="color:var(--gains);">↑</span>'
    if series[-1] < series[0]:
        return '<span style="color:var(--losses);">↓</span>'
    return '<span style="color:var(--text-muted);">→</span>'


def render_ratio_card(
    *,
    label: str,
    value: Optional[float],
    history: Optional[Sequence[float]] = None,
    avg_10y: Optional[float] = None,
    industry_avg: Optional[float] = None,
    kind: ValueKind = "pct",
    higher_better: bool = True,
    sector: Optional[str] = None,
) -> None:
    """
    Render a single ratio card. ``history`` triggers a small sparkline
    via ``st.line_chart`` underneath the headline.

    When ``sector`` is provided, the card asks the BenchmarkEngine for
    a sector comparison and renders a stacked badge underneath the
    headline (in addition to or in place of the explicit
    ``industry_avg`` row).
    """
    # Optional benchmark lookup — keeps the card useful even when the
    # caller doesn't have ``industry_avg`` precomputed.
    cmp = None
    if sector is not None:
        try:
            from analysis.benchmark_engine import compare_to_sector
            cmp = compare_to_sector(label, value, sector)
            if cmp is not None and industry_avg is None:
                industry_avg = cmp.benchmark_value
        except Exception:
            cmp = None

    color = _color_for_value(value, industry_avg, higher_better=higher_better)
    value_text = _fmt_value(value, kind)
    avg_text = _fmt_value(avg_10y, kind)
    ind_text = _fmt_value(industry_avg, kind)
    trend = _trend_arrow(history)

    parts = [
        '<div class="eq-card" style="padding:14px 16px; min-height:160px;">',
        f'<div class="eq-idx-label">{label.upper()}</div>',
        f'<div style="font-size:28px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{value_text}</div>',
        '<div style="height:1px; background:var(--border); margin:10px 0;"></div>',
        '<div style="display:flex; flex-direction:column; gap:4px; '
        'font-size:11px; color:var(--text-muted); letter-spacing:0.3px;">',
        f'<div style="display:flex; justify-content:space-between;">'
        f'<span>10Y AVG</span><span style="color:var(--text-secondary); '
        f'font-variant-numeric:tabular-nums;">{avg_text}</span></div>',
        f'<div style="display:flex; justify-content:space-between;">'
        f'<span>INDUSTRY AVG</span><span style="color:var(--text-secondary); '
        f'font-variant-numeric:tabular-nums;">{ind_text}</span></div>',
        f'<div style="display:flex; justify-content:space-between;">'
        f'<span>TREND</span><span style="font-size:13px;">{trend or "—"}</span></div>',
        '</div>',
        '</div>',
    ]
    st.markdown("".join(parts), unsafe_allow_html=True)

    # Optional stacked benchmark badge — only when sector + a valid
    # comparison were resolved by the engine.
    if cmp is not None and cmp.benchmark_value is not None:
        try:
            from ui.components.benchmark_badge import render_benchmark_badge
            render_benchmark_badge(cmp, inline=False)
        except Exception:
            pass

    # Sparkline as a separate native st.line_chart — Streamlit hides the
    # axes when height is small. Skip when history is empty.
    if history and any(v is not None for v in history):
        try:
            df = pd.DataFrame({"v": [v if v is not None else 0 for v in history]})
            st.line_chart(df, height=60, use_container_width=True)
        except Exception:
            pass
