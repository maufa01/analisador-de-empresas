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
            "Change %{customdata[0]:+.2f}%<br>"
            "ETF %{customdata[1]} · $%{customdata[2]:,.2f}"
            "<extra></extra>"
        ),
        customdata=np.stack([
            df["change_pct"].values,
            df["etf"].values,
            df["last"].values,
        ], axis=-1),
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
    on_select=None,
    height: int = 240,
) -> None:
    """
    Render the heatmap + a row of "click to filter" links underneath.

    Plotly Treemap clicks aren't reliably surfaced in Streamlit yet, so
    we expose a parallel row of small buttons (one per sector) that the
    page wires to the movers-table sector filter.
    """
    fig = build_sector_heatmap_figure(sectors, height=height)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    if on_select is None or sectors is None or sectors.empty:
        return

    df = sectors.dropna(subset=["change_pct"])
    cols = st.columns(len(df))
    for col, (_, r) in zip(cols, df.iterrows()):
        with col:
            label = r["sector"].split(" ")[0]            # short label fits the col
            if st.button(
                label, key=f"sector_pick_{r['sector']}",
                type="secondary", use_container_width=True,
                help=f"Filter movers to {r['sector']}",
            ):
                on_select(r["sector"])
                st.rerun()
