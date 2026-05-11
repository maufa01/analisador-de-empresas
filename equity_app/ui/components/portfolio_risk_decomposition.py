"""Portfolio risk decomposition — marginal contribution to risk per holding."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_risk_decomposition(
    returns: pd.DataFrame,
    weights: dict[str, float],
) -> None:
    if returns is None or returns.empty:
        st.info("Risk decomposition needs returns data.")
        return
    if not weights:
        st.info("Risk decomposition needs weights.")
        return

    # Align tickers present in BOTH inputs
    tickers = [t for t in weights if t in returns.columns]
    if len(tickers) < 2:
        st.info("Need 2+ holdings with price history for risk decomposition.")
        return

    rets = returns[tickers].dropna(how="any")
    if len(rets) < 30:
        st.info("Need at least 30 overlapping return observations.")
        return

    # Normalise weights to the surviving tickers
    raw = np.array([weights[t] for t in tickers], dtype=float)
    if raw.sum() <= 0:
        st.info("Weights sum to zero on the surviving tickers.")
        return
    w = raw / raw.sum()

    cov = rets.cov().loc[tickers, tickers].values * 252.0  # annualised
    vols = np.sqrt(np.diag(cov))
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(port_var) if port_var > 0 else float("nan")

    # MCTR_i = w_i * (Σ w)_i / σ_p   (contribution in vol units)
    cov_w = cov @ w
    mctr = w * cov_w / port_vol if port_vol > 0 else np.zeros_like(w)
    # % contribution sums to 1 (or 100%) by definition: MCTR / port_vol
    pct_contrib = (mctr / port_vol * 100.0) if port_vol > 0 else np.zeros_like(w)

    # Beta of each holding to the portfolio
    port_rets = (rets * w).sum(axis=1)
    var_port = float(port_rets.var(ddof=1)) if len(port_rets) > 1 else 0.0
    betas = []
    for t in tickers:
        cov_ip = float(rets[t].cov(port_rets))
        betas.append(cov_ip / var_port if var_port > 0 else float("nan"))

    # ---- Bar chart: weight vs risk contribution side by side ----
    weight_pct = w * 100.0
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=tickers, y=weight_pct, name="Weight %",
        marker_color="rgba(110,123,139,0.75)",  # neutral gray
        hovertemplate="<b>%{x}</b><br>Weight %{y:.1f}%<extra></extra>",
    ))
    # Highlight bars where risk contribution > 2× weight
    risk_colors = [
        "rgba(230,57,70,0.85)" if pct_contrib[i] > 2 * weight_pct[i]
        else "rgba(201,161,74,0.85)"
        for i in range(len(tickers))
    ]
    fig.add_trace(go.Bar(
        x=tickers, y=pct_contrib, name="Risk contribution %",
        marker_color=risk_colors,
        hovertemplate="<b>%{x}</b><br>Risk contribution %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        barmode="group",
        height=320, margin=dict(l=50, r=20, t=30, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=11,
                  color="rgba(255,255,255,0.85)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=10)),
        xaxis=dict(showgrid=False, tickfont=dict(size=10),
                   color="rgba(255,255,255,0.55)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   ticksuffix="%", tickfont=dict(size=10),
                   color="rgba(255,255,255,0.55)"),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Table ----
    df = pd.DataFrame({
        "Ticker": tickers,
        "Weight %": weight_pct,
        "Annualised vol %": vols * 100.0,
        "Risk contribution %": pct_contrib,
        "Beta to portfolio": betas,
    })
    df = df.sort_values("Risk contribution %", ascending=False)
    st.dataframe(
        df, hide_index=True, use_container_width=True,
        column_config={
            "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
            "Annualised vol %": st.column_config.NumberColumn(format="%.1f%%"),
            "Risk contribution %": st.column_config.NumberColumn(format="%.1f%%"),
            "Beta to portfolio": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    st.caption(
        f"Portfolio annualised vol: **{port_vol*100:.1f}%**. A position "
        "with risk contribution >2× its weight is dominating portfolio "
        "variance (highlighted red) — often a cyclical or high-vol "
        "holding hidden within larger weights."
    )
