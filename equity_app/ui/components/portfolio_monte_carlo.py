"""
Monte Carlo wealth projection for an optimized portfolio.

Bootstraps the historical daily portfolio-return series ``n_simulations``
times across an ``years_horizon``-year horizon and visualises the
fan chart of cumulative wealth (5/25/50/75/95 percentiles) along with
a summary table.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


_PERCENTILES = (5, 25, 50, 75, 95)
_TRADING_DAYS = 252


def _simulate(
    portfolio_returns: pd.Series,
    *,
    n_simulations: int,
    years: int,
    initial_wealth: float,
    seed: Optional[int],
) -> np.ndarray:
    """Bootstrap returns and return a 2-D array (n_sims, n_periods+1) of wealth."""
    r = portfolio_returns.dropna().values
    if r.size == 0:
        return np.zeros((0, 0))
    n_periods = years * _TRADING_DAYS
    rng = np.random.default_rng(seed)
    draws = rng.choice(r, size=(int(n_simulations), n_periods), replace=True)
    wealth = np.cumprod(1.0 + draws, axis=1) * float(initial_wealth)
    # Prepend column of starting wealth so the fan starts on day 0
    starts = np.full((draws.shape[0], 1), float(initial_wealth))
    return np.hstack([starts, wealth])


def render_portfolio_monte_carlo(
    portfolio_returns: pd.Series,
    *,
    years: int = 10,
    n_simulations: int = 5000,
    initial_wealth: float = 10_000.0,
    height: int = 360,
    seed: int = 42,
) -> None:
    if portfolio_returns is None or portfolio_returns.dropna().empty:
        st.info("Cannot project — portfolio return history is empty.")
        return

    paths = _simulate(
        portfolio_returns,
        n_simulations=n_simulations, years=years,
        initial_wealth=initial_wealth, seed=seed,
    )
    if paths.size == 0:
        st.warning("Bootstrap simulation produced no paths.")
        return

    pcts = np.percentile(paths, _PERCENTILES, axis=0)
    days = np.arange(paths.shape[1])
    years_axis = days / _TRADING_DAYS

    # Fan chart — three filled bands + median line
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years_axis, y=pcts[4],
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip", name="_p95",
    ))
    fig.add_trace(go.Scatter(
        x=years_axis, y=pcts[0],
        fill="tonexty", fillcolor="rgba(201,169,97,0.10)",
        line=dict(color="rgba(0,0,0,0)"),
        name="P5–P95", showlegend=True,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=years_axis, y=pcts[3],
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip", name="_p75",
    ))
    fig.add_trace(go.Scatter(
        x=years_axis, y=pcts[1],
        fill="tonexty", fillcolor="rgba(201,169,97,0.20)",
        line=dict(color="rgba(0,0,0,0)"),
        name="P25–P75", showlegend=True,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=years_axis, y=pcts[2],
        line=dict(color=ACCENT, width=2),
        name="Median",
        hovertemplate="<b>Year %{x:.1f}</b><br>$%{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(title=dict(text="Years", font=dict(color=TEXT_MUTED)),
                   color=TEXT_MUTED, showgrid=False, zeroline=False),
        yaxis=dict(title=dict(text="Wealth ($)", font=dict(color=TEXT_MUTED)),
                   color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, tickprefix="$", tickformat=",.0f"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Summary table
    final = paths[:, -1]
    cagr_per_path = (final / initial_wealth) ** (1.0 / years) - 1.0
    summary = pd.DataFrame({
        "Statistic":      ["Pessimistic (P5)",
                           "P25",
                           "Median",
                           "P75",
                           "Optimistic (P95)"],
        "Final wealth":   [
            f"${np.percentile(final, 5):,.0f}",
            f"${np.percentile(final, 25):,.0f}",
            f"${np.percentile(final, 50):,.0f}",
            f"${np.percentile(final, 75):,.0f}",
            f"${np.percentile(final, 95):,.0f}",
        ],
        "CAGR":           [
            f"{np.percentile(cagr_per_path, 5) * 100:+.2f}%",
            f"{np.percentile(cagr_per_path, 25) * 100:+.2f}%",
            f"{np.percentile(cagr_per_path, 50) * 100:+.2f}%",
            f"{np.percentile(cagr_per_path, 75) * 100:+.2f}%",
            f"{np.percentile(cagr_per_path, 95) * 100:+.2f}%",
        ],
    })
    st.dataframe(summary, hide_index=True, use_container_width=True)

    # Probability of loss across the horizon
    p_loss = float((final < initial_wealth).mean())
    st.caption(
        f"Probability of ending below the initial $"
        f"{initial_wealth:,.0f}: **{p_loss * 100:.1f}%**  ·  "
        f"{n_simulations:,} bootstrapped paths over {years} years."
    )
