"""
Two-panel chart for backtests: cumulative-return curve on top,
underwater drawdown on the bottom.

Both panels are tied to the same x-axis. The portfolio is drawn in the
gold accent; the (optional) benchmark is drawn in muted text colour for
contrast without distracting.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, LOSSES, LOSSES_FILL,
)


def _drawdown(returns: pd.Series) -> pd.Series:
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    wealth = (1.0 + returns.fillna(0.0)).cumprod()
    peak = wealth.cummax()
    return wealth / peak - 1.0


def build_backtest_figure(
    portfolio_returns: pd.Series,
    *,
    benchmark_returns: Optional[pd.Series] = None,
    portfolio_label: str = "Portfolio",
    benchmark_label: str = "Benchmark",
    height: int = 420,
) -> go.Figure:
    """
    Top panel: cumulative wealth (start = 1.0).
    Bottom panel: portfolio drawdown (underwater, filled).
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.06,
    )

    if portfolio_returns is None or portfolio_returns.empty:
        _empty_layout(fig, height)
        return fig

    p_wealth = (1.0 + portfolio_returns.fillna(0.0)).cumprod()
    fig.add_trace(go.Scatter(
        x=p_wealth.index, y=p_wealth.values,
        mode="lines", line=dict(color=ACCENT, width=2),
        name=portfolio_label,
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>"
                      f"{portfolio_label}: %{{y:,.3f}}x<extra></extra>",
    ), row=1, col=1)

    if benchmark_returns is not None and not benchmark_returns.empty:
        b_wealth = (1.0 + benchmark_returns.fillna(0.0)).cumprod()
        fig.add_trace(go.Scatter(
            x=b_wealth.index, y=b_wealth.values,
            mode="lines",
            line=dict(color=TEXT_SECONDARY, width=1.5, dash="dot"),
            name=benchmark_label,
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>"
                          f"{benchmark_label}: %{{y:,.3f}}x<extra></extra>",
        ), row=1, col=1)

    dd = _drawdown(portfolio_returns) * 100
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values,
        mode="lines",
        line=dict(color=LOSSES, width=1.5),
        fill="tozeroy", fillcolor=LOSSES_FILL,
        name="Drawdown",
        hovertemplate="<b>%{x|%b %d, %Y}</b><br>DD: %{y:.2f}%<extra></extra>",
        showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
    )
    fig.update_xaxes(color=TEXT_MUTED, showgrid=False, zeroline=False, showline=False)
    fig.update_yaxes(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                     zeroline=False, showline=False, side="right")
    fig.update_yaxes(title=dict(text="Wealth (×)", font=dict(color=TEXT_MUTED)),
                     row=1, col=1)
    fig.update_yaxes(title=dict(text="Drawdown (%)", font=dict(color=TEXT_MUTED)),
                     ticksuffix="%", row=2, col=1)
    return fig


def _empty_layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=0, r=0, t=10, b=0),
        annotations=[dict(
            text="No backtest data", showarrow=False,
            font=dict(color=TEXT_MUTED, size=12),
            x=0.5, y=0.5, xref="paper", yref="paper",
        )],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
