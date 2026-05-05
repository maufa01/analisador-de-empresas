"""
Correlation heatmap of the portfolio's return series.

Plotly heatmap with a diverging red→white→green colour scale capped at
±1. Diagonal is grey (each asset's correlation with itself = 1, which
the user already knows). Hover shows the exact value.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    GAINS, LOSSES,
)


def render_correlation_heatmap(returns: pd.DataFrame, *, height: int = 380) -> None:
    if returns is None or returns.empty:
        st.info("No return series available for correlation analysis.")
        return

    corr = returns.corr().round(2)
    n = len(corr)
    if n < 2:
        st.info("Need at least 2 assets to compute a correlation matrix.")
        return

    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns, y=corr.index,
        zmin=-1.0, zmax=1.0,
        colorscale=[
            [0.0,  LOSSES],
            [0.5,  TEXT_MUTED],
            [1.0,  GAINS],
        ],
        text=corr.values,
        texttemplate="%{text:.2f}",
        textfont=dict(family="Inter, sans-serif", size=11, color=TEXT_PRIMARY),
        hovertemplate="<b>%{y}</b> ↔ <b>%{x}</b><br>ρ = %{z:.2f}<extra></extra>",
        colorbar=dict(
            tickfont=dict(color=TEXT_MUTED, size=10),
            outlinewidth=0, thickness=8, len=0.85,
        ),
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(side="top", color=TEXT_MUTED, showgrid=False, zeroline=False),
        yaxis=dict(autorange="reversed", color=TEXT_MUTED, showgrid=False, zeroline=False),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # High-correlation cluster warning — enumerate upper-triangle pairs
    high_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(corr.iat[i, j]) > 0.85:
                high_pairs.append((corr.index[i], corr.columns[j], corr.iat[i, j]))
    if high_pairs:
        bullets = "".join(
            f'<li><b>{a}</b> ↔ <b>{b}</b>: ρ = {r:+.2f}</li>'
            for a, b, r in high_pairs[:5]
        )
        st.markdown(
            '<div style="color:var(--text-secondary); font-size:12px; '
            'margin-top:8px;">High-correlation pairs (limit diversification):'
            f'<ul style="margin-top:4px; padding-left:18px;">{bullets}</ul>'
            '</div>',
            unsafe_allow_html=True,
        )
