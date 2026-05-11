"""Portfolio correlation heatmap with hierarchical clustering order."""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _cluster_order(corr: pd.DataFrame) -> list[str]:
    """Return tickers reordered by hierarchical clustering (Ward linkage)
    on 1−corr distance. Falls back to original order if scipy missing."""
    try:
        from scipy.cluster.hierarchy import linkage, leaves_list
        # Distance: 1 - |corr| keeps similar (positive OR negative) close.
        dist = 1.0 - corr.abs().values
        np.fill_diagonal(dist, 0.0)
        # Use the upper triangle as a condensed distance vector
        from scipy.spatial.distance import squareform
        cond = squareform(dist, checks=False)
        z = linkage(cond, method="average")
        idx = leaves_list(z)
        return [corr.columns[i] for i in idx]
    except Exception:
        return list(corr.columns)


def _avg_color(avg: float) -> str:
    if avg < 0.30:
        return "var(--gains)"
    if avg < 0.60:
        return "var(--accent)"
    return "rgba(184,115,51,1)"


def render_correlation_heatmap(returns: pd.DataFrame) -> None:
    if returns is None or returns.empty or len(returns.columns) < 2:
        st.info("Correlation needs 2+ tickers with overlapping price history.")
        return

    corr = returns.corr().dropna(how="all").dropna(axis=1, how="all")
    if corr.empty or len(corr) < 2:
        st.info("Not enough overlapping observations to compute correlations.")
        return

    order = _cluster_order(corr)
    corr = corr.loc[order, order]

    # App-aligned diverging palette: teal (negative corr — assets move
    # opposite) → dark surface (zero) → coral (high positive corr —
    # functionally one position). Stops on the −1..+1 axis.
    app_colorscale = [
        [0.00, "#2EC4B6"],   # −1.0 teal (COLOR_GROWTH)
        [0.25, "#1F7A6F"],   # −0.5 darker teal
        [0.50, "#131826"],   # 0.0 dark surface (matches app bg)
        [0.75, "#8B5C2C"],   # +0.5 muted copper
        [1.00, "#E63946"],   # +1.0 coral (COLOR_NEGATIVE)
    ]

    # Plotly heatmap with diverging palette
    z = corr.values
    text = [[f"{z[i, j]:.2f}" for j in range(z.shape[1])]
            for i in range(z.shape[0])]
    fig = go.Figure(go.Heatmap(
        z=z, x=order, y=order,
        zmin=-1, zmax=1,
        colorscale=app_colorscale, reversescale=False,
        text=text, texttemplate="%{text}",
        textfont=dict(size=10, color="rgba(255,255,255,0.95)"),
        hovertemplate="<b>%{x}</b> ↔ <b>%{y}</b>: %{z:.2f}<extra></extra>",
        colorbar=dict(
            thickness=10, len=0.8,
            tickfont=dict(size=10, color="rgba(255,255,255,0.55)"),
        ),
    ))
    fig.update_layout(
        height=max(280, 36 * len(order) + 80),
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=11,
                  color="rgba(255,255,255,0.85)"),
        xaxis=dict(side="bottom", tickangle=0,
                   tickfont=dict(size=10, color="rgba(255,255,255,0.55)")),
        yaxis=dict(autorange="reversed",
                   tickfont=dict(size=10, color="rgba(255,255,255,0.55)")),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Avg pairwise correlation (excl. diagonal) ----
    mask = np.triu(np.ones_like(z, dtype=bool), k=1)
    upper = z[mask]
    if upper.size > 0:
        avg = float(np.nanmean(upper))
        color = _avg_color(avg)
        st.markdown(
            f'<div data-testid="stMetric" style="margin-top:6px;">'
            f'<div style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.6px; text-transform:uppercase;">'
            f'AVG PAIRWISE CORRELATION</div>'
            f'<div style="color:{color}; font-size:24px; font-weight:500; '
            f'letter-spacing:-0.3px; margin-top:2px;">{avg:+.2f}</div></div>',
            unsafe_allow_html=True,
        )

    st.caption(
        "Average pairwise correlation indicates structural diversification. "
        "Above 0.60: positions tend to move together; the portfolio is "
        "functionally less diversified than the holding count suggests."
    )
