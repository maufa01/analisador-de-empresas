"""
Sector breakdown for an optimized portfolio — donut + table.

Maps each ticker to its GICS sector via ``data.constituents.META``.
Tickers not in the curated universe land in an ``Other`` bucket so the
chart still totals 100%.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.constituents import META as TICKER_META
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT,
    GAINS, LOSSES,
)


# Per-sector palette — accent shades for the donut. Picked so adjacent
# slices stay distinguishable on the dark background.
_SECTOR_COLORS: dict[str, str] = {
    "Technology":             ACCENT,
    "Healthcare":             "#9C8C5A",
    "Financials":             "#5BA48A",
    "Consumer Discretionary": "#7B7CC2",
    "Consumer Staples":       "#B98F6E",
    "Communication Services": "#8E8E93",
    "Industrials":            "#6E9DBC",
    "Energy":                 "#C45942",
    "Utilities":              "#4F8C7A",
    "Materials":              "#A05A6E",
    "Real Estate":            "#7C8A5E",
    "Other":                  TEXT_MUTED,
}


def _aggregate(weights: pd.Series) -> pd.Series:
    """Group weights by GICS sector. Unknown tickers go to 'Other'."""
    by_sector: dict[str, float] = {}
    for ticker, w in weights.items():
        if w is None or w <= 0:
            continue
        sector = TICKER_META.get(ticker.upper(), {}).get("sector", "Other")
        by_sector[sector] = by_sector.get(sector, 0.0) + float(w)
    s = pd.Series(by_sector, name="weight")
    return s.sort_values(ascending=False)


def render_sector_breakdown(weights: pd.Series, *, height: int = 320) -> None:
    """Donut chart on the left + concentration table on the right."""
    aggregated = _aggregate(weights)
    if aggregated.empty:
        st.info("No active positions to break down by sector.")
        return

    col_l, col_r = st.columns([1.2, 1])

    with col_l:
        colors = [_SECTOR_COLORS.get(s, TEXT_MUTED) for s in aggregated.index]
        fig = go.Figure(go.Pie(
            labels=list(aggregated.index),
            values=(aggregated.values * 100),
            hole=0.55,
            marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
            sort=False,
            textposition="outside",
            textinfo="label+percent",
            textfont=dict(family="Inter, sans-serif", size=11, color=TEXT_PRIMARY),
            hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
        ))
        fig.update_layout(
            height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    with col_r:
        df = aggregated.reset_index().rename(columns={"index": "Sector"})
        df["Weight %"] = df["weight"] * 100.0
        df = df[["Sector", "Weight %"]]
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

        # Concentration warning when any sector >40%
        if aggregated.iloc[0] > 0.40:
            st.markdown(
                f'<div style="color:var(--losses); font-size:12px; '
                f'margin-top:8px;">⚠ Concentration risk: '
                f'{aggregated.index[0]} = {aggregated.iloc[0] * 100:.1f}%</div>',
                unsafe_allow_html=True,
            )
