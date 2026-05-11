"""Reinvestment Rate — CapEx / Revenue per year.

Surfaces capital intensity over time. Software / asset-light businesses
sit at 2-5%; semi heavy at 15-25%; utilities and telcos at 20%+.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get
from ui.charts import (
    CHART_HEIGHT, COLOR_PRIMARY, COLOR_REFERENCE, COLOR_TEXT_MUTED,
    _annotate_last, _base_layout, _empty_layout, _fy_labels,
)


def build_reinvestment_rate(
    income: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty or cash is None or cash.empty:
        fig.update_layout(**_empty_layout(
            "Reinvestment data unavailable", height=height,
        ))
        return fig

    revenue = _get(income, "revenue")
    capex = _get(cash, "capex")
    # The column may exist with all-NaN values (SEC mapping ships an
    # empty `capitalExpenditure` for some tickers, e.g. NVDA FY22-26).
    # Treat that as "missing" for reporting purposes.
    missing: list[str] = []
    if revenue is None or revenue.dropna().empty:
        missing.append("revenue")
    if capex is None or capex.dropna().empty:
        missing.append("capitalExpenditure")
    if missing:
        fig.update_layout(**_empty_layout(
            f"Reinvestment rate needs: {', '.join(missing)}",
            height=height,
        ))
        return fig

    # Align series; drop years with non-positive revenue (ratio undefined)
    # or missing capex. Negative capex is the FMP/SEC convention — take abs.
    aligned = pd.DataFrame({"rev": revenue, "capex": capex.abs()}).dropna()
    aligned = aligned[aligned["rev"] > 0]
    if aligned.empty:
        fig.update_layout(**_empty_layout(
            "No overlapping revenue + capex data", height=height,
        ))
        return fig

    aligned["rate"] = aligned["capex"] / aligned["rev"]
    aligned = aligned.tail(5)

    x = _fy_labels(aligned.index)
    y_pct = (aligned["rate"].values * 100.0)
    fig.add_trace(go.Bar(
        x=x, y=y_pct,
        name="CapEx / Revenue",
        marker_color=COLOR_PRIMARY,
        hovertemplate="<b>%{x}</b><br>CapEx / Revenue %{y:.1f}%<extra></extra>",
        showlegend=False,
    ))
    _annotate_last(fig, x, y_pct,
                   label=f"{aligned['rate'].iloc[-1]:.1%}",
                   color=COLOR_PRIMARY)

    layout = _base_layout(
        height=height, y_title="CapEx / Revenue", y_ticksuffix="%",
    )
    fig.update_layout(**layout)

    # 5y average reference line — only when we have >= 3 valid points
    # (an average over 1-2 years isn't really an average).
    if len(aligned) >= 3:
        avg = float(aligned["rate"].mean())
        fig.add_hline(
            y=avg * 100.0,
            line_dash="dot", line_color=COLOR_REFERENCE, opacity=0.7,
            annotation_text=f"5y avg {avg:.1%}",
            annotation_position="top right",
            annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
        )
    return fig
