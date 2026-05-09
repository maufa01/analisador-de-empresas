"""ui.charts package — shared styling helpers for buyside-quality charts.

Every chart in the Charts tab MUST consume `_base_layout()` and
`_fy_labels()` so the visual grammar (font, gridlines, x-axis ticks,
legend) stays consistent.
"""
from __future__ import annotations
from typing import Iterable, Optional, Sequence

import pandas as pd
import plotly.graph_objects as go


# ============================================================
# Visual tokens — match the dark-theme palette of the wider app
# ============================================================
CHART_HEIGHT = 320
CHART_FONT = "Inter, system-ui, -apple-system, sans-serif"

COLOR_PRIMARY    = "#C9A14A"   # gold — revenue, $ amounts, capital
COLOR_GROWTH     = "#2EC4B6"   # teal — FCF, growth, net income
COLOR_NEGATIVE   = "#E63946"   # coral — debt, decline, risk
COLOR_NEUTRAL    = "#6E7B8B"   # gray — secondary
COLOR_REFERENCE  = "rgba(255,255,255,0.35)"  # dashed reference lines
COLOR_GRID       = "rgba(255,255,255,0.06)"
COLOR_TEXT_MUTED = "rgba(255,255,255,0.55)"
COLOR_TEXT_BODY  = "rgba(255,255,255,0.85)"


# ============================================================
# Layout
# ============================================================
def _base_layout(
    title: Optional[str] = None,
    *,
    dual_axis: bool = False,
    height: int = CHART_HEIGHT,
    y_title: Optional[str] = None,
    y_tickprefix: Optional[str] = None,
    y_ticksuffix: Optional[str] = None,
) -> dict:
    """Shared Plotly layout. type='category' on x-axis is critical —
    integer-string year labels otherwise get treated as numeric and
    Plotly inserts decimal ticks (2021.5, etc.)."""
    layout: dict = dict(
        height=height,
        margin=dict(l=50, r=20, t=30 if title else 10, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=CHART_FONT, size=11, color=COLOR_TEXT_BODY),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(19,24,38,0.95)",
            bordercolor="rgba(255,255,255,0.1)",
            font=dict(color=COLOR_TEXT_BODY, size=12, family=CHART_FONT),
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=10, color=COLOR_TEXT_MUTED),
            type="category",
        ),
        yaxis=dict(
            showgrid=True, gridcolor=COLOR_GRID,
            tickfont=dict(size=10, color=COLOR_TEXT_MUTED),
            zeroline=True, zerolinecolor=COLOR_GRID, zerolinewidth=1,
        ),
    )
    if title:
        layout["title"] = dict(
            text=title, x=0.0, xanchor="left",
            font=dict(size=12, color=COLOR_TEXT_BODY, family=CHART_FONT),
        )
    if y_title:
        layout["yaxis"]["title"] = dict(
            text=y_title, font=dict(size=10, color=COLOR_TEXT_MUTED),
        )
    if y_tickprefix:
        layout["yaxis"]["tickprefix"] = y_tickprefix
    if y_ticksuffix:
        layout["yaxis"]["ticksuffix"] = y_ticksuffix
    if dual_axis:
        layout["yaxis2"] = dict(
            overlaying="y", side="right",
            showgrid=False,
            tickfont=dict(size=10, color=COLOR_TEXT_MUTED),
        )
    return layout


# ============================================================
# X-axis labelling
# ============================================================
def _fy_labels(periods: Iterable) -> list[str]:
    """Convert period_end timestamps/strings to consistent 'FY YYYY' labels."""
    out: list[str] = []
    for p in periods:
        try:
            ts = pd.Timestamp(p)
            out.append(f"FY {ts.year}")
        except Exception:
            out.append(str(p)[:7])
    return out


# ============================================================
# Annotations
# ============================================================
def _annotate_last(
    fig: go.Figure,
    x: Sequence,
    y: Sequence,
    *,
    label: str,
    color: str,
    yref: str = "y",
) -> None:
    """Direct-label the last point of a series. Use on key metrics so
    the legend can be hidden."""
    if not x or y is None or len(y) == 0:
        return
    fig.add_annotation(
        x=x[-1], y=y[-1], yref=yref,
        text=f"<b>{label}</b>",
        showarrow=False, xanchor="left", xshift=6,
        font=dict(size=10, color=color, family=CHART_FONT),
    )


def _empty_layout(message: str = "No data available", *, height: int = CHART_HEIGHT) -> dict:
    """Layout for empty charts — no axes, centered message."""
    return dict(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(
            text=message, showarrow=False,
            x=0.5, y=0.5, xref="paper", yref="paper",
            font=dict(color=COLOR_TEXT_MUTED, size=12, family=CHART_FONT),
        )],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )


# ============================================================
# Math
# ============================================================
def _cagr(first: Optional[float], last: Optional[float], periods: int) -> Optional[float]:
    """CAGR helper. Returns decimal (0.12 = 12%). None if invalid."""
    if first is None or last is None or first <= 0 or last <= 0 or periods <= 0:
        return None
    try:
        return (last / first) ** (1 / periods) - 1
    except (ValueError, ZeroDivisionError):
        return None
