"""Owner Earnings (Buffett-style) vs Free Cash Flow."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import owner_earnings, free_cash_flow
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_PRIMARY, COLOR_REFERENCE,
    COLOR_TEXT_MUTED, _annotate_last, _base_layout, _empty_layout, _fy_labels,
)


def build_owner_earnings_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    fig = go.Figure()

    oe = owner_earnings(income, balance, cash)
    fcf = free_cash_flow(cash)

    # Build the full chronological x-axis up front so the categorical
    # axis doesn't reorder entries by "first seen" (otherwise FY with
    # NaN in OE — typical when D&A rolling avg needs lookback — ends up
    # at the right end after FCF introduces it).
    full_idx: pd.Index = pd.Index([])
    if oe is not None:
        full_idx = full_idx.union(oe.dropna().index)
    if fcf is not None:
        full_idx = full_idx.union(fcf.dropna().index)
    full_x = _fy_labels(sorted(full_idx))

    plotted = 0
    if oe is not None:
        s = oe.dropna()
        if not s.empty:
            x = _fy_labels(s.index)
            y = (s.values / 1e9)
            fig.add_trace(go.Bar(
                x=x, y=y,
                name="Owner Earnings",
                marker_color=COLOR_PRIMARY,
                hovertemplate="<b>%{x}</b><br>Owner Earnings $%{y:,.2f}B<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, y,
                           label=f"OE ${y[-1]:,.1f}B", color=COLOR_PRIMARY)

            # 5y average reference line
            avg = float(s.tail(5).mean()) / 1e9
            if avg > 0:
                fig.add_hline(
                    y=avg, line_dash="dash", line_color=COLOR_REFERENCE,
                    opacity=0.7,
                    annotation_text=f"5y avg ${avg:,.1f}B",
                    annotation_position="bottom right",
                    annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
                )
            plotted += 1

    if fcf is not None:
        s = fcf.dropna()
        if not s.empty:
            x = _fy_labels(s.index)
            y = (s.values / 1e9)
            fig.add_trace(go.Scatter(
                x=x, y=y,
                name="Free Cash Flow",
                line=dict(color=COLOR_GROWTH, width=2, dash="dot"),
                marker=dict(size=6),
                mode="lines+markers",
                hovertemplate="<b>%{x}</b><br>FCF $%{y:,.2f}B<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, y,
                           label=f"FCF ${y[-1]:,.1f}B", color=COLOR_GROWTH)
            plotted += 1

    if plotted == 0:
        fig.update_layout(**_empty_layout("Owner Earnings unavailable", height=height))
        return fig

    layout = _base_layout(height=height, y_tickprefix="$", y_ticksuffix="B")
    if full_x:
        layout["xaxis"]["categoryorder"] = "array"
        layout["xaxis"]["categoryarray"] = full_x
    fig.update_layout(**layout)
    return fig
