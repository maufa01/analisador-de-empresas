"""Cash Conversion — FCF / Net Income per year.

Tracks earnings quality: > 1.0x means free cash flow outpaces accounting
net income (high quality); < 0.8x sustained is a red flag — earnings
that aren't converting to cash.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, free_cash_flow
from ui.charts import (
    CHART_HEIGHT, COLOR_PRIMARY, COLOR_REFERENCE, COLOR_TEXT_MUTED,
    _annotate_last, _base_layout, _empty_layout, _fy_labels,
)


def build_cash_conversion(
    income: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty or cash is None or cash.empty:
        fig.update_layout(**_empty_layout(
            "Cash conversion unavailable", height=height,
        ))
        return fig

    ni = _get(income, "net_income")
    fcf = free_cash_flow(cash)
    if ni is None or fcf is None:
        # Be explicit which input is missing so the caller can fix the
        # data layer rather than mask it.
        missing = []
        if ni is None:
            missing.append("net_income")
        if fcf is None:
            missing.append("freeCashFlow / (operatingCashFlow − capitalExpenditure)")
        fig.update_layout(**_empty_layout(
            f"Cash conversion needs: {', '.join(missing)}",
            height=height,
        ))
        return fig

    # Align series and drop years where NI ≤ 0 (ratio is meaningless
    # when NI is negative — leaves a visual gap, intentional).
    aligned = pd.DataFrame({"ni": ni, "fcf": fcf}).dropna()
    aligned = aligned[aligned["ni"] > 0]
    if aligned.empty:
        fig.update_layout(**_empty_layout(
            "No positive net income to compute conversion", height=height,
        ))
        return fig

    aligned["conv"] = aligned["fcf"] / aligned["ni"]
    aligned = aligned.tail(5)

    x = _fy_labels(aligned.index)
    y = aligned["conv"].values
    fig.add_trace(go.Bar(
        x=x, y=y,
        name="FCF / NI",
        marker_color=COLOR_PRIMARY,
        hovertemplate="<b>%{x}</b><br>FCF / NI %{y:.2f}x<extra></extra>",
        showlegend=False,
    ))
    _annotate_last(fig, x, y, label=f"{y[-1]:.2f}x", color=COLOR_PRIMARY)

    layout = _base_layout(
        height=height, y_title="FCF / Net Income (x)", y_ticksuffix="x",
    )
    fig.update_layout(**layout)

    # 1.0x parity reference line
    fig.add_hline(
        y=1.0, line_dash="dash", line_color=COLOR_REFERENCE, opacity=0.7,
        annotation_text="1.0x parity",
        annotation_position="top right",
        annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
    )
    return fig
