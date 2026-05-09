"""
Visual badges that surface sector-benchmark context next to ratio values.

Two render modes:
- ``inline=True``  → compact pill (rendered alongside a ratio value)
- ``inline=False`` → stacked block with sector avg + interpretation

Plus :func:`render_benchmark_summary_table` for a multi-ratio overview.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from analysis.benchmark_engine import BenchmarkComparison


_ARROWS: dict[str, str] = {
    "far_above": "↑↑",
    "above":     "↑",
    "in_line":   "≈",
    "below":     "↓",
    "far_below": "↓↓",
}

_LABELS: dict[str, str] = {
    "far_above": "Top quartile",
    "above":     "Above sector",
    "in_line":   "In line",
    "below":     "Below sector",
    "far_below": "Bottom quartile",
}


def render_benchmark_badge(
    cmp: Optional[BenchmarkComparison],
    inline: bool = True,
) -> None:
    """Render a sector-comparison badge next to a ratio."""
    if cmp is None or cmp.benchmark_value is None:
        return

    arrow = _ARROWS[cmp.position]
    label = _LABELS[cmp.position]
    # Performance label — "Top quartile" only makes sense for favorable
    # outcomes. Flip when the value direction is unfavorable.
    fav_label = label
    if cmp.position in ("far_above", "above") and not cmp.higher_is_better:
        fav_label = "Bottom quartile" if cmp.position == "far_above" else "Below sector"
    elif cmp.position in ("far_below", "below") and not cmp.higher_is_better:
        fav_label = "Top quartile" if cmp.position == "far_below" else "Above sector"

    if inline:
        html = (
            f'<div style="display:inline-flex; align-items:center; gap:6px; '
            f'padding:2px 8px; background:{cmp.color}20; '
            f'border:1px solid {cmp.color}; border-radius:4px; '
            f'font-size:11px; color:{cmp.color};">'
            f'<span style="font-weight:600;">{arrow}</span>'
            f'<span>{fav_label}</span>'
            f'<span style="color:#9CA3AF;">vs {cmp.sector}</span>'
            f'</div>'
        )
    else:
        html = (
            f'<div style="border-left:3px solid {cmp.color}; '
            f'padding-left:12px; margin-top:4px;">'
            f'<div style="color:#6B7280; font-size:10px; '
            f'text-transform:uppercase; letter-spacing:0.5px;">'
            f'{cmp.sector} sector avg'
            f'</div>'
            f'<div style="display:flex; gap:12px; align-items:baseline; '
            f'margin-top:2px;">'
            f'<span style="color:#E8EAED; font-size:14px; font-weight:500; '
            f'font-variant-numeric:tabular-nums;">'
            f'{cmp.benchmark_value:.2f}'
            f'</span>'
            f'<span style="color:{cmp.color}; font-size:12px;">'
            f'{cmp.interpretation}'
            f'</span>'
            f'</div>'
            f'</div>'
        )
    st.markdown(html, unsafe_allow_html=True)


def render_benchmark_summary_table(
    comparisons: dict[str, BenchmarkComparison],
    title: str = "vs Sector",
) -> None:
    """Render a single table with one row per ratio comparison."""
    if not comparisons:
        return

    rows_html: list[str] = []
    for name, cmp in comparisons.items():
        gap_str = (f"{cmp.gap:+.2f}"
                   if cmp.gap is not None else "—")
        bench_str = (f"{cmp.benchmark_value:.2f}"
                     if cmp.benchmark_value is not None else "—")
        rows_html.append(
            '<tr style="border-top:1px solid #1F2937;">'
            f'<td style="padding:8px 12px; color:#E8EAED;">{name}</td>'
            f'<td style="padding:8px 12px; text-align:right; '
            f'color:#E8EAED; font-variant-numeric:tabular-nums;">'
            f'{cmp.value:.2f}</td>'
            f'<td style="padding:8px 12px; text-align:right; '
            f'color:#9CA3AF; font-variant-numeric:tabular-nums;">'
            f'{bench_str}</td>'
            f'<td style="padding:8px 12px; text-align:right; '
            f'color:{cmp.color}; font-variant-numeric:tabular-nums;">'
            f'{gap_str}</td>'
            f'<td style="padding:8px 12px; color:{cmp.color}; '
            f'font-size:12px;">{cmp.interpretation}</td>'
            '</tr>'
        )

    table = (
        '<div style="background:#131826; border:1px solid #1F2937; '
        'border-radius:8px; overflow:auto; padding:12px 0;">'
        f'<div style="color:#6B7280; font-size:11px; text-transform:uppercase;'
        f' letter-spacing:0.6px; padding:0 12px 8px 12px;">{title}</div>'
        '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
        '<thead><tr style="color:#6B7280; font-size:10px; '
        'text-transform:uppercase; letter-spacing:0.5px;">'
        '<th style="text-align:left; padding:8px 12px;">Ratio</th>'
        '<th style="text-align:right; padding:8px 12px;">Value</th>'
        '<th style="text-align:right; padding:8px 12px;">Sector</th>'
        '<th style="text-align:right; padding:8px 12px;">Gap</th>'
        '<th style="text-align:left; padding:8px 12px;">vs Sector</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows_html) + '</tbody></table></div>'
    )
    st.markdown(table, unsafe_allow_html=True)
