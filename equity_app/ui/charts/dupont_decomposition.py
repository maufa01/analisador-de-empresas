"""DuPont decomposition — ROE = Net Margin × Asset Turnover × Equity Multiplier.

Four lines on a dual axis: NM and derived ROE on the left (percent),
AT and EM on the right (ratio). Lets the reader see *why* ROE moved —
margin expansion vs asset efficiency vs leverage.

We deliberately use ending-period balance values (not beginning+ending
averages) so the decomposition is reproducible from any single year's
filings.
"""
from __future__ import annotations
import logging

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_PRIMARY,
    COLOR_TEXT_MUTED, _annotate_last, _base_layout, _empty_layout, _fy_labels,
)

log = logging.getLogger(__name__)


def build_dupont(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty or balance is None or balance.empty:
        fig.update_layout(**_empty_layout(
            "DuPont data unavailable", height=height,
        ))
        return fig

    ni  = _get(income, "net_income")
    rev = _get(income, "revenue")
    ta  = _get(balance, "total_assets")
    eq  = _get(balance, "total_equity")

    missing: list[str] = []
    for label, series in (
        ("netIncome", ni), ("revenue", rev),
        ("totalAssets", ta), ("totalStockholdersEquity", eq),
    ):
        if series is None or series.dropna().empty:
            missing.append(label)
    if missing:
        fig.update_layout(**_empty_layout(
            f"DuPont needs: {', '.join(missing)}", height=height,
        ))
        return fig

    # Align all 4 series on common index
    df = pd.DataFrame({"ni": ni, "rev": rev, "ta": ta, "eq": eq}).dropna()

    # Filter years with non-positive denominators (negative equity in
    # particular makes the multiplier explode — skip and log).
    skipped_eq = df[df["eq"] <= 0]
    if not skipped_eq.empty:
        log.warning(
            "DuPont: skipped %d year(s) with non-positive equity at %s",
            len(skipped_eq), [str(d) for d in skipped_eq.index],
        )
    valid = df[(df["rev"] > 0) & (df["ta"] > 0) & (df["eq"] > 0)]
    if valid.empty:
        fig.update_layout(**_empty_layout(
            "DuPont: no years with positive revenue / assets / equity",
            height=height,
        ))
        return fig

    valid = valid.tail(5).copy()
    valid["nm"]  = valid["ni"]  / valid["rev"]                     # decimal
    valid["at"]  = valid["rev"] / valid["ta"]                      # ratio
    valid["em"]  = valid["ta"]  / valid["eq"]                      # ratio
    valid["roe"] = valid["nm"]  * valid["at"]  * valid["em"]       # decimal

    x = _fy_labels(valid.index)

    # ---- Left axis (%) ----
    # ROE first — thick headline line, plotted under NM so the marker
    # stays visible.
    roe_pct = (valid["roe"].values * 100.0)
    fig.add_trace(go.Scatter(
        x=x, y=roe_pct, name="ROE",
        line=dict(color=COLOR_NEGATIVE, width=3),
        marker=dict(size=8),
        mode="lines+markers",
        hovertemplate="<b>%{x}</b><br>ROE %{y:.2f}%<extra></extra>",
    ))
    _annotate_last(fig, x, roe_pct,
                   label=f"ROE {valid['roe'].iloc[-1]:.1%}",
                   color=COLOR_NEGATIVE)

    nm_pct = (valid["nm"].values * 100.0)
    fig.add_trace(go.Scatter(
        x=x, y=nm_pct, name="Net Margin",
        line=dict(color=COLOR_PRIMARY, width=2),
        marker=dict(size=6),
        mode="lines+markers",
        hovertemplate="<b>%{x}</b><br>Net Margin %{y:.2f}%<extra></extra>",
    ))
    _annotate_last(fig, x, nm_pct,
                   label=f"NM {valid['nm'].iloc[-1]:.1%}",
                   color=COLOR_PRIMARY)

    # ---- Right axis (× ratio) ----
    at_vals = valid["at"].values
    fig.add_trace(go.Scatter(
        x=x, y=at_vals, name="Asset Turnover",
        line=dict(color=COLOR_GROWTH, width=2),
        marker=dict(size=6),
        mode="lines+markers",
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Asset Turnover %{y:.2f}x<extra></extra>",
    ))
    _annotate_last(fig, x, at_vals,
                   label=f"AT {at_vals[-1]:.2f}x",
                   color=COLOR_GROWTH, yref="y2")

    em_vals = valid["em"].values
    fig.add_trace(go.Scatter(
        x=x, y=em_vals, name="Equity Multiplier",
        line=dict(color=COLOR_NEUTRAL, width=2),
        marker=dict(size=6),
        mode="lines+markers",
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Equity Multiplier %{y:.2f}x<extra></extra>",
    ))
    _annotate_last(fig, x, em_vals,
                   label=f"EM {em_vals[-1]:.2f}x",
                   color=COLOR_NEUTRAL, yref="y2")

    # ---- Layout ----
    layout = _base_layout(height=height, dual_axis=True, y_ticksuffix="%")
    layout["yaxis2"]["ticksuffix"] = "x"
    # 4 series + 2 axes → need a clear legend. Put it top-center.
    layout["legend"] = dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="center", x=0.5,
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=10),
    )
    fig.update_layout(**layout)

    # Identity annotation (top-right corner)
    fig.add_annotation(
        xref="paper", yref="paper",
        x=1.0, y=1.12, xanchor="right", yanchor="bottom",
        showarrow=False,
        text="<b>ROE = NM × AT × EM</b>",
        font=dict(size=9, color=COLOR_TEXT_MUTED),
    )

    # Sanity check: derived (ending-equity) ROE vs direct NI/Equity.
    # Difference >10% usually means avg-vs-ending convention or a
    # restated equity column — log it, don't surface in UI.
    last = valid.iloc[-1]
    if float(last["eq"]) != 0:
        direct = float(last["ni"]) / float(last["eq"])
        derived = float(last["roe"])
        if direct != 0:
            diff = abs((derived - direct) / direct)
            if diff > 0.10:
                log.warning(
                    "DuPont sanity check: derived ROE diverges from direct by %.1f%% "
                    "(derived %.3f vs direct %.3f) — likely avg-vs-ending convention",
                    diff * 100, derived, direct,
                )

    return fig
