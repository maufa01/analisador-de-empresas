"""
Cash Conversion Cycle chart for the Charts tab.

A slim figure-only renderer (no cards, no interpretation) on top of
:func:`analysis.working_capital.compute_ccc_history`. Distinct from
``ui/components/ccc_chart.py`` which is the FULL dashboard (cards +
interpretation + chart) shown on the Capital allocation tab.

CCC is rendered as a thick gold line; DSO / DIO / DPO sit underneath as
thin dotted reference lines so the user can decompose the move. A dashed
zero line marks the "collects before paying" threshold.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.working_capital import compute_ccc_history
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE, TEXT_MUTED, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"


def build_ccc_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    *,
    height: int = 400,
) -> go.Figure:
    history = compute_ccc_history(income=income, balance=balance)

    fig = go.Figure()

    if history.empty:
        fig.update_layout(
            height=height,
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            font=dict(color=TEXT_SECONDARY),
            annotations=[dict(
                text="CCC not computable — receivables, inventory, "
                     "payables, or COGS missing.",
                showarrow=False, x=0.5, y=0.5,
                xref="paper", yref="paper",
                font=dict(color=TEXT_MUTED, size=12),
            )],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        return fig

    components = [
        ("DSO", "#3B82F6"),
        ("DIO", ACCENT),
        ("DPO", GAINS),
    ]
    for col, color in components:
        if col not in history.columns:
            continue
        s = history[col].dropna()
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            mode="lines+markers",
            name=col,
            line=dict(color=color, width=1.5, dash="dot"),
            marker=dict(size=5),
            opacity=0.7,
        ))

    if "CCC" in history.columns:
        s = history["CCC"].dropna()
        if not s.empty:
            last3 = s.tail(3).values
            trend_up = len(last3) >= 2 and last3[-1] > last3[0]
            ccc_color = _DOWNSIDE if trend_up else GAINS
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values,
                mode="lines+markers+text",
                name="CCC",
                line=dict(color=ccc_color, width=3),
                marker=dict(size=8),
                text=[f"{v:.0f}d" for v in s.values],
                textposition="top center",
                textfont=dict(size=10, color=ccc_color),
            ))

    fig.add_hline(
        y=0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.6,
        annotation_text="CCC = 0 (collects before paying)",
        annotation_position="bottom right",
        annotation_font=dict(size=10, color=TEXT_MUTED),
    )

    fig.update_layout(
        title=dict(text="Cash Conversion Cycle (days)",
                   font=dict(color=TEXT_SECONDARY, size=14)),
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        height=height,
        yaxis=dict(title="Days", gridcolor=BORDER, color=TEXT_MUTED,
                   zeroline=False, ticksuffix="d"),
        xaxis=dict(gridcolor=BORDER, color=TEXT_MUTED),
        legend=dict(orientation="h", yanchor="top", y=1.12),
        margin=dict(l=0, r=10, t=50, b=20),
    )
    return fig


def build_ccc_breakdown_table(
    income: pd.DataFrame,
    balance: pd.DataFrame,
) -> pd.DataFrame:
    """Tabular view of DSO / DIO / DPO / CCC by year — fits below the chart."""
    history = compute_ccc_history(income=income, balance=balance)
    if history.empty:
        return pd.DataFrame()
    return history.round(1)
