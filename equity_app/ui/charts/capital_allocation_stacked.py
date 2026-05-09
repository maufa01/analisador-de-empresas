"""Capital allocation — stacked bar of CapEx / Buybacks / Dividends /
Acquisitions, with FCF overlay so the user sees if deployment exceeds
operating cash generation."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get, free_cash_flow
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_PRIMARY,
    _base_layout, _empty_layout, _fy_labels,
)


def build_capital_allocation_chart(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = 380,
) -> go.Figure:
    fig = go.Figure()
    if cash is None or cash.empty:
        fig.update_layout(**_empty_layout("Cash flow data unavailable", height=height))
        return fig

    capex     = _get(cash, "capex")
    buybacks  = _get(cash, "buybacks")
    dividends = _get(cash, "dividends_paid")

    # acquisitions: no alias exists in ratios.py — try common column names
    acq: Optional[pd.Series] = None
    for col in ("acquisitionsNet", "acquisitions_net", "Acquisitions Net"):
        if col in cash.columns:
            try:
                acq = cash[col].astype(float)
                break
            except (ValueError, TypeError):
                continue

    components = [
        ("CapEx",        capex,     COLOR_NEUTRAL),
        ("Buybacks",     buybacks,  COLOR_PRIMARY),
        ("Dividends",    dividends, COLOR_GROWTH),
        ("Acquisitions", acq,       COLOR_NEGATIVE),
    ]

    plotted = 0
    common_index: pd.Index | None = None
    for _, series, _ in components:
        if series is None:
            continue
        s = series.dropna()
        if s.empty:
            continue
        common_index = s.index if common_index is None else common_index.union(s.index)

    if common_index is None or len(common_index) == 0:
        fig.update_layout(**_empty_layout("No capital deployment data", height=height))
        return fig

    common_index = pd.Index(sorted(common_index))
    x = _fy_labels(common_index)

    for label, series, color in components:
        if series is None:
            continue
        s = series.reindex(common_index).dropna()
        if s.empty:
            continue
        # Cash-flow components are reported as negative outflows; show as
        # positive absolute magnitudes so the stack reads cleanly.
        values = (s.abs() / 1e9)
        fig.add_trace(go.Bar(
            x=_fy_labels(values.index), y=values.values,
            name=label, marker_color=color,
            hovertemplate=f"<b>%{{x}}</b><br>{label} $%{{y:,.2f}}B<extra></extra>",
        ))
        plotted += 1

    # FCF overlay (line) — context for whether deployment is within means
    fcf = free_cash_flow(cash)
    if fcf is not None:
        s = fcf.reindex(common_index).dropna()
        if not s.empty:
            fig.add_trace(go.Scatter(
                x=_fy_labels(s.index), y=(s.values / 1e9),
                mode="lines+markers", name="FCF",
                line=dict(color="rgba(255,255,255,0.6)", width=2, dash="dot"),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>FCF $%{y:,.2f}B<extra></extra>",
            ))

    if plotted == 0:
        fig.update_layout(**_empty_layout("No capital deployment data", height=height))
        return fig

    layout = _base_layout(
        height=height, y_tickprefix="$", y_ticksuffix="B",
    )
    layout["barmode"] = "stack"
    fig.update_layout(**layout)
    return fig
