"""
Sector performance heatmap — Plotly treemap of the 11 GICS sectors,
with cells sized by a market-cap proxy and coloured by today's % change
(red → grey → green).

Falls back to a flat HTML grid when the input DataFrame is empty so the
section never collapses to a blank line.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GAINS, LOSSES, ACCENT,
)


def _empty_state(height: int) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=0, b=0),
        annotations=[dict(
            text="No sector data available",
            showarrow=False,
            font=dict(color=TEXT_MUTED, size=12),
            x=0.5, y=0.5, xref="paper", yref="paper",
        )],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def build_sector_heatmap_figure(
    sectors: pd.DataFrame,
    *,
    height: int = 240,
) -> go.Figure:
    """
    Args:
        sectors: DataFrame with columns ``sector``, ``etf``, ``last``,
                 ``change_pct``, ``market_cap``.
    """
    if sectors is None or sectors.empty:
        return _empty_state(height)

    df = sectors.dropna(subset=["change_pct"]).copy()
    if df.empty:
        return _empty_state(height)

    # Cap colour range symmetrically so a 0% day reads as the neutral
    # grey from the global border colour rather than a weird mid-tone.
    cmax = max(2.5, float(df["change_pct"].abs().max()))

    # Build labels with two lines (sector name + change %)
    sign = lambda v: "+" if v >= 0 else ""  # noqa: E731
    text_lines = [
        f"<b>{r['sector'].upper()}</b><br>{sign(r['change_pct'])}{r['change_pct']:.2f}%"
        for _, r in df.iterrows()
    ]

    fig = go.Figure(go.Treemap(
        labels=df["sector"],
        parents=[""] * len(df),
        values=df["market_cap"].clip(lower=1.0),     # avoid zero areas
        text=text_lines,
        textinfo="text",
        textfont=dict(family="Inter, sans-serif", size=12, color=TEXT_PRIMARY),
        marker=dict(
            colors=df["change_pct"],
            colorscale=[
                [0.0, LOSSES],
                [0.5, BORDER],
                [1.0, GAINS],
            ],
            cmin=-cmax, cmax=cmax,
            line=dict(color=SURFACE, width=2),
            showscale=False,
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Change %{customdata[0]}<br>"
            "ETF %{customdata[1]} · %{customdata[2]}"
            "<extra></extra>"
        ),
        # Pre-format every customdata value as a string. ``np.stack`` on a
        # mix of float + string columns coerces everything to object dtype,
        # which Plotly's "%{customdata[i]:+.2f}" format specifier silently
        # ignores — that's how the tooltip ended up showing
        # "0.917588665299296%" with 15 decimals instead of "+0.92%".
        customdata=[
            [f"{cp:+.2f}%", etf, f"${last:,.2f}"]
            for cp, etf, last in zip(
                df["change_pct"].values,
                df["etf"].values,
                df["last"].values,
            )
        ],
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
    )
    return fig


def render_sector_heatmap(
    sectors: pd.DataFrame,
    *,
    height: int = 240,
    on_select=None,                          # kept for backwards compat; unused
) -> None:
    """
    Render the heatmap. The "click a button to filter movers" row that
    used to live below was removed — labels were getting truncated and
    the duplicate "Consumer" pills (Discretionary vs Staples both
    starting with the same word) made the grid confusing. The sector
    pills under TOP MOVERS already cover that filter.
    """
    fig = build_sector_heatmap_figure(sectors, height=height)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})
