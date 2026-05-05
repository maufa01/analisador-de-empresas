"""
Efficient frontier scatter — frontier line, individual assets, and the
selected portfolio (max-Sharpe star).

Inputs are pre-computed: ``frontier`` is the DataFrame returned by
``portfolio.optimizer.efficient_frontier`` and ``assets`` carries the
per-asset (vol, return) projections. ``selected`` highlights one chosen
portfolio (typically max-Sharpe).
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS,
)


def build_frontier_figure(
    frontier: pd.DataFrame,
    *,
    assets: Optional[pd.DataFrame] = None,
    selected: Optional[dict] = None,
    height: int = 380,
) -> go.Figure:
    """
    Args:
        frontier: columns ``volatility``, ``return`` (annualized).
        assets: optional DataFrame with index = ticker and columns
                ``volatility`` & ``return`` for the per-asset dots.
        selected: optional dict with keys ``volatility``, ``return``,
                  ``label`` to draw a highlighted star.
    """
    fig = go.Figure()
    if frontier is None or frontier.empty:
        _empty_layout(fig, height)
        return fig

    fig.add_trace(go.Scatter(
        x=frontier["volatility"], y=frontier["return"],
        mode="lines",
        line=dict(color=ACCENT, width=2),
        name="Efficient frontier",
        hovertemplate=(
            "Vol %{x:.2%}<br>"
            "Ret %{y:.2%}<br>"
            "Sharpe %{customdata:.3f}<extra></extra>"
        ),
        customdata=frontier["sharpe"] if "sharpe" in frontier.columns else None,
    ))

    if assets is not None and not assets.empty:
        fig.add_trace(go.Scatter(
            x=assets["volatility"], y=assets["return"],
            mode="markers+text",
            marker=dict(color=TEXT_SECONDARY, size=8, symbol="circle",
                        line=dict(color=BORDER, width=1)),
            text=list(assets.index),
            textposition="top center",
            textfont=dict(color=TEXT_MUTED, size=10),
            name="Assets",
            hovertemplate="<b>%{text}</b><br>Vol %{x:.2%}<br>Ret %{y:.2%}<extra></extra>",
        ))

    if selected:
        label = selected.get("label", "Selected")
        fig.add_trace(go.Scatter(
            x=[selected["volatility"]], y=[selected["return"]],
            mode="markers",
            marker=dict(color=GAINS, size=16, symbol="star",
                        line=dict(color=TEXT_PRIMARY, width=1)),
            name=label,
            hovertemplate=(
                f"<b>{label}</b><br>"
                "Vol %{x:.2%}<br>Ret %{y:.2%}<extra></extra>"
            ),
        ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="closest",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(
            title=dict(text="Volatility (annualized)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
            tickformat=".0%", zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Expected return (annualized)", font=dict(color=TEXT_MUTED)),
            color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
            tickformat=".0%", zeroline=False,
        ),
    )
    return fig


def _empty_layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(
            text="No frontier data", showarrow=False,
            font=dict(color=TEXT_MUTED, size=12),
            x=0.5, y=0.5, xref="paper", yref="paper",
        )],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
