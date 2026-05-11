"""ROIC / ROCE / ROA evolution — three lines, consistent palette."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, roic, roa
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEUTRAL, COLOR_PRIMARY,
    COLOR_REFERENCE, COLOR_TEXT_MUTED, _annotate_last, _base_layout,
    _empty_layout, _fy_labels,
)


def _roce(income: pd.DataFrame, balance: pd.DataFrame):
    ebit = _get(income, "ebit")
    ta = _get(balance, "total_assets")
    cl = _get(balance, "current_liabilities")
    if ebit is None or ta is None or cl is None:
        return None
    capital_employed = ta - cl
    return ebit / capital_employed.replace(0, pd.NA)


def build_profitability_evolution(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
    wacc: Optional[float] = None,
) -> go.Figure:
    fig = go.Figure()

    series = [
        ("ROIC", roic(income, balance), COLOR_GROWTH),
        ("ROCE", _roce(income, balance), COLOR_PRIMARY),
        ("ROA",  roa(income, balance),   COLOR_NEUTRAL),
    ]

    plotted = 0
    last_roic_pct: float | None = None
    for label, raw, color in series:
        if raw is None:
            continue
        s = raw.dropna()
        if s.empty:
            continue
        x = _fy_labels(s.index)
        y_pct = (s.values * 100.0)
        fig.add_trace(go.Scatter(
            x=x, y=y_pct,
            mode="lines+markers", name=label,
            line=dict(color=color, width=2),
            marker=dict(size=6),
            hovertemplate=f"<b>%{{x}}</b><br>{label} %{{y:.1f}}%<extra></extra>",
            showlegend=False,
        ))
        _annotate_last(fig, x, y_pct,
                       label=f"{label} {y_pct[-1]:.0f}%", color=color)
        if label == "ROIC":
            last_roic_pct = float(y_pct[-1])
        plotted += 1

    if plotted == 0:
        fig.update_layout(**_empty_layout("No profitability data", height=height))
        return fig

    fig.update_layout(**_base_layout(height=height, y_ticksuffix="%"))

    # WACC reference — dashed horizontal. Spread between ROIC and WACC
    # is the cleanest visual for "is this company creating value?".
    if wacc is not None and wacc > 0:
        wacc_pct = float(wacc) * 100.0
        fig.add_hline(
            y=wacc_pct, line_dash="dash", line_color=COLOR_REFERENCE,
            opacity=0.7,
            annotation_text=f"WACC ≈ {wacc_pct:.1f}%",
            annotation_position="bottom right",
            annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
        )

    # Anomaly note: ROIC > 50% is mathematically valid but typically
    # signals reduced book equity from buybacks (e.g. AAPL FY24/25).
    # Surface it so the reader doesn't take a 100%+ ROIC at face value.
    if last_roic_pct is not None and last_roic_pct > 50:
        fig.add_annotation(
            xref="paper", yref="paper",
            x=1.0, y=1.06,
            xanchor="right", yanchor="bottom",
            showarrow=False,
            text="ROIC inflated by reduced book equity (buybacks)",
            font=dict(size=9, color=COLOR_TEXT_MUTED),
        )
    return fig
