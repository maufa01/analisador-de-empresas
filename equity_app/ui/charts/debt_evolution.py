"""Debt evolution — D/A and Net Debt/EBITDA. Kd shown as scalar headline
when fewer than 3 valid points (a 2-point line is misleading)."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get
from ui.charts import (
    CHART_HEIGHT, COLOR_NEGATIVE, COLOR_PRIMARY, COLOR_REFERENCE,
    COLOR_TEXT_MUTED, _annotate_last, _base_layout, _empty_layout, _fy_labels,
)


def _resolve_total_debt(balance: pd.DataFrame) -> Optional[pd.Series]:
    """LT + ST debt fallback (mirrors ratios._resolve_total_debt)."""
    debt = _get(balance, "total_debt")
    if debt is not None:
        return debt
    ltd = _get(balance, "long_term_debt")
    std = _get(balance, "short_term_debt")
    if ltd is None and std is None:
        return None
    if ltd is None:
        return std
    if std is None:
        return ltd
    return ltd.add(std, fill_value=0.0)


def build_debt_evolution(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()

    debt = _resolve_total_debt(balance)
    ta = _get(balance, "total_assets")
    ebitda = _get(income, "ebitda")
    cash_eq = _get(balance, "cash_eq")
    interest = _get(income, "interest_expense")

    if debt is None:
        fig.update_layout(**_empty_layout("Debt data unavailable", height=height))
        return fig

    plotted = 0

    # D/A
    if ta is not None:
        da = (debt / ta.replace(0, pd.NA)).dropna()
        if not da.empty:
            x = _fy_labels(da.index)
            y = (da.values * 100.0)
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines+markers", name="D/A",
                line=dict(color=COLOR_NEGATIVE, width=2),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>D/A %{y:.1f}%<extra></extra>",
                showlegend=False,
            ))
            _annotate_last(fig, x, y,
                           label=f"D/A {y[-1]:.1f}%", color=COLOR_NEGATIVE)
            plotted += 1

    # Net Debt / EBITDA (use net debt — gross debt is misleading for cash-rich names)
    if ebitda is not None:
        net_debt = debt - (cash_eq if cash_eq is not None else 0.0)
        nde = (net_debt / ebitda.replace(0, pd.NA)).dropna()
        if not nde.empty:
            x = _fy_labels(nde.index)
            y = nde.values
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines+markers", name="Net Debt/EBITDA",
                line=dict(color=COLOR_PRIMARY, width=2),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>Net Debt/EBITDA %{y:.2f}x<extra></extra>",
                showlegend=False,
                yaxis="y2",
            ))
            _annotate_last(fig, x, y,
                           label=f"Net Debt/EBITDA {y[-1]:.1f}x",
                           color=COLOR_PRIMARY, yref="y2")
            plotted += 1

    if plotted == 0:
        fig.update_layout(**_empty_layout("Debt data unavailable", height=height))
        return fig

    layout = _base_layout(height=height, dual_axis=True, y_ticksuffix="%")
    layout["yaxis2"]["ticksuffix"] = "x"
    fig.update_layout(**layout)

    # Reference line: Net Debt/EBITDA = 3.0x is the conventional "high
    # leverage" threshold (see Moody's / S&P median).
    fig.add_hline(
        y=3.0, line_dash="dash", line_color=COLOR_REFERENCE, opacity=0.7,
        yref="y2",
        annotation_text="3.0x · high leverage",
        annotation_position="bottom right",
        annotation_font=dict(size=9, color=COLOR_TEXT_MUTED),
    )

    # Cost of Debt as scalar headline when too few points to make a line.
    if interest is not None:
        avg_debt = ((debt + debt.shift(1)) / 2)
        kd_series = (interest.abs() / avg_debt.replace(0, pd.NA)).dropna()
        if not kd_series.empty:
            kd_latest = float(kd_series.iloc[-1]) * 100.0
            fig.add_annotation(
                xref="paper", yref="paper",
                x=0.0, y=1.06, xanchor="left", yanchor="bottom",
                showarrow=False,
                text=f"Cost of debt (latest): {kd_latest:.1f}%",
                font=dict(size=10, color=COLOR_TEXT_MUTED),
            )
    return fig
