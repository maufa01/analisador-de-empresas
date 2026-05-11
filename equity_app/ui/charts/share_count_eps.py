"""Share Count + Diluted EPS — dual-axis chart.

Bars (left axis): diluted weighted-average share count.
Line (right axis): diluted EPS.

The combination separates the *per-share* story from the *net-income*
story: even when NI grows, buybacks amplify EPS; conversely, dilution
can mask earnings progress.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from analysis.ratios import _get
from ui.charts import (
    CHART_HEIGHT, COLOR_GROWTH, COLOR_PRIMARY, COLOR_TEXT_MUTED,
    _annotate_last, _base_layout, _cagr, _empty_layout, _fy_labels,
)


def build_share_count_eps(
    income: pd.DataFrame,
    *,
    height: int = CHART_HEIGHT,
) -> go.Figure:
    fig = go.Figure()
    if income is None or income.empty:
        fig.update_layout(**_empty_layout(
            "Share count data unavailable", height=height,
        ))
        return fig

    # Diluted shares — alias chain in ratios.py explicitly excludes the
    # `weightedAverageShsOutBasic` column, so we honour "diluted only"
    # without ever silently using basic as a fallback.
    shares = _get(income, "weighted_avg_shares")
    eps = _get(income, "eps_diluted")

    missing: list[str] = []
    if shares is None or shares.dropna().empty:
        missing.append("weightedAverageShsOutDil")
    if eps is None or eps.dropna().empty:
        missing.append("epsDiluted")
    if missing:
        fig.update_layout(**_empty_layout(
            f"Share / EPS chart needs: {', '.join(missing)}",
            height=height,
        ))
        return fig

    # Build aligned 5y window. Shares ≤ 0 is meaningless — drop those
    # years. EPS may be negative (loss period) — keep, plot the dip.
    aligned = pd.DataFrame({"shares": shares, "eps": eps})
    aligned = aligned[(aligned["shares"].notna()) & (aligned["shares"] > 0)]
    aligned = aligned.tail(5)
    if aligned.empty:
        fig.update_layout(**_empty_layout(
            "Share count data unavailable", height=height,
        ))
        return fig

    x = _fy_labels(aligned.index)

    # Dynamic unit scaling — most large caps sit in B, small/mid in M.
    shares_max = float(aligned["shares"].max())
    if shares_max >= 1e9:
        divisor, unit = 1e9, "B"
        last_label = f"{aligned['shares'].iloc[-1] / divisor:.2f}{unit}"
    else:
        divisor, unit = 1e6, "M"
        last_label = f"{aligned['shares'].iloc[-1] / divisor:.0f}{unit}"

    shares_scaled = aligned["shares"].values / divisor
    fig.add_trace(go.Bar(
        x=x, y=shares_scaled,
        name="Diluted shares",
        marker_color=COLOR_PRIMARY,
        hovertemplate=f"<b>%{{x}}</b><br>Shares %{{y:.2f}}{unit}<extra></extra>",
        showlegend=False,
    ))
    _annotate_last(fig, x, shares_scaled,
                   label=last_label, color=COLOR_PRIMARY)

    # EPS trace — keep all years including negatives so loss periods
    # show as a dip rather than disappearing.
    eps_vals = aligned["eps"].values
    fig.add_trace(go.Scatter(
        x=x, y=eps_vals,
        name="Diluted EPS",
        mode="lines+markers",
        line=dict(color=COLOR_GROWTH, width=2),
        marker=dict(size=7),
        hovertemplate="<b>%{x}</b><br>EPS $%{y:.2f}<extra></extra>",
        showlegend=False,
        yaxis="y2",
    ))
    last_eps = aligned["eps"].dropna()
    if not last_eps.empty:
        _annotate_last(fig, x, eps_vals,
                       label=f"${float(last_eps.iloc[-1]):.2f}",
                       color=COLOR_GROWTH, yref="y2")

    # Top-right summary annotation: shares change + EPS CAGR.
    n = len(aligned)
    notes: list[str] = []
    if n >= 2:
        s_first = float(aligned["shares"].iloc[0])
        s_last = float(aligned["shares"].iloc[-1])
        if s_first > 0:
            share_chg = (s_last / s_first - 1.0)
            notes.append(f"Shares: {share_chg:+.1%} {n - 1}y")

        eps_clean = aligned["eps"].dropna()
        if len(eps_clean) >= 2:
            eps_first = float(eps_clean.iloc[0])
            eps_last = float(eps_clean.iloc[-1])
            if eps_first <= 0 or eps_last <= 0:
                notes.append("EPS: not meaningful (loss period)")
            else:
                g = _cagr(eps_first, eps_last, len(eps_clean) - 1)
                if g is not None:
                    notes.append(f"EPS CAGR: {g:.1%}")
    if notes:
        fig.add_annotation(
            xref="paper", yref="paper",
            x=1.0, y=1.06, xanchor="right", yanchor="bottom",
            showarrow=False,
            text="<b>" + "  ·  ".join(notes) + "</b>",
            font=dict(size=10, color=COLOR_TEXT_MUTED),
        )

    layout = _base_layout(
        height=height, dual_axis=True,
        y_title=f"Diluted shares ({unit})",
        y_ticksuffix=unit,
    )
    layout["yaxis2"]["title"] = dict(
        text="Diluted EPS ($)", font=dict(size=10, color=COLOR_TEXT_MUTED),
    )
    layout["yaxis2"]["tickprefix"] = "$"
    fig.update_layout(**layout)
    return fig
