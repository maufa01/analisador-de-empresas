"""Cash Conversion Cycle chart for the Charts tab.

CCC as the headline thick line; DSO / DIO / DPO as thin dotted reference
lines underneath. Zero-day reference line marks "collects before paying".
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.working_capital import compute_ccc_history
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_PRIMARY,
    COLOR_REFERENCE, COLOR_TEXT_MUTED, _annotate_last, _base_layout,
    _empty_layout, _fy_labels,
)


def build_ccc_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    *,
    height: int = 400,
) -> go.Figure:
    fig = go.Figure()
    history = compute_ccc_history(income=income, balance=balance)
    if history.empty:
        fig.update_layout(**_empty_layout(
            "CCC not computable — receivables, inventory, payables, or COGS missing.",
            height=height,
        ))
        return fig

    # Component reference lines (faint, dotted)
    components = [
        ("DSO", COLOR_NEUTRAL),
        ("DIO", COLOR_PRIMARY),
        ("DPO", COLOR_GROWTH),
    ]
    for col, color in components:
        if col not in history.columns:
            continue
        s = history[col].dropna()
        if s.empty:
            continue
        x = _fy_labels(s.index)
        fig.add_trace(go.Scatter(
            x=x, y=s.values,
            mode="lines+markers", name=col,
            line=dict(color=color, width=1.5, dash="dot"),
            marker=dict(size=5),
            opacity=0.7,
            hovertemplate=f"<b>%{{x}}</b><br>{col} %{{y:.0f}}d<extra></extra>",
            showlegend=False,
        ))

    # CCC headline line
    if "CCC" in history.columns:
        s = history["CCC"].dropna()
        if not s.empty:
            last3 = s.tail(3).values
            trend_up = len(last3) >= 2 and last3[-1] > last3[0]
            ccc_color = COLOR_NEGATIVE if trend_up else COLOR_GROWTH
            x = _fy_labels(s.index)
            y = s.values
            fig.add_trace(go.Scatter(
                x=x, y=y,
                mode="lines+markers", name="CCC",
                line=dict(color=ccc_color, width=3),
                marker=dict(size=7),
                hovertemplate="<b>%{x}</b><br>CCC %{y:.0f}d<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, y,
                           label=f"CCC {y[-1]:.0f}d", color=ccc_color)

    layout = _base_layout(height=height, y_ticksuffix="d", y_title="Days")
    fig.update_layout(**layout)

    fig.add_hline(
        y=0, line_dash="dash", line_color=COLOR_REFERENCE, opacity=0.6,
        annotation_text="CCC = 0 (collects before paying)",
        annotation_position="bottom right",
        annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
    )
    return fig


def build_ccc_breakdown_table(
    income: pd.DataFrame,
    balance: pd.DataFrame,
) -> pd.DataFrame:
    """Tabular DSO / DIO / DPO / CCC by year — fits below the chart."""
    history = compute_ccc_history(income=income, balance=balance)
    if history.empty:
        return pd.DataFrame()
    return history.round(1)
