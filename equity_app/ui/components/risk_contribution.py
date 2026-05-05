"""
Risk-contribution table — showing how much of total portfolio variance
each position contributes (vs its capital weight).

The classic insight: a 22% NVDA stake can drive 41% of portfolio risk
when its vol is double the average. The dual-bar visualisation makes
the imbalance obvious.

Risk contribution share for asset i:
    RC_i = w_i × (Σ w)_i / σ²_p
where σ²_p = w' Σ w.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st


def compute_risk_contribution(
    weights: pd.Series,
    cov: pd.DataFrame,
) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by ticker with columns:
        weight · vol · risk_contrib · marginal_risk
    All as decimals (0.227 = 22.7%).
    """
    cols = list(weights.index)
    w = weights.values
    sigma = cov.reindex(index=cols, columns=cols).values
    port_var = float(w @ sigma @ w)
    if port_var <= 0:
        return pd.DataFrame()

    marginal = sigma @ w                        # ∂σ²_p / ∂w_i
    contrib = w * marginal / port_var           # share of total variance
    asset_vol = np.sqrt(np.diag(sigma))
    df = pd.DataFrame({
        "weight":          w,
        "vol":             asset_vol,
        "risk_contrib":    contrib,
        "marginal_risk":   marginal,
    }, index=cols)
    return df.sort_values("risk_contrib", ascending=False)


def render_risk_contribution(
    weights: pd.Series,
    cov: pd.DataFrame,
) -> None:
    df = compute_risk_contribution(weights, cov)
    if df.empty:
        st.info("Cannot compute risk contributions for this portfolio.")
        return

    # Filter out near-zero weights to keep the table compact
    df = df[df["weight"] > 1e-3].copy()

    display = pd.DataFrame({
        "Ticker":        df.index,
        "Weight %":      df["weight"] * 100,
        "Vol %":         df["vol"] * 100,
        "Risk contrib %": df["risk_contrib"] * 100,
        "Marginal risk": df["marginal_risk"],
    })
    st.dataframe(
        display, hide_index=True, use_container_width=True,
        column_config={
            "Weight %":        st.column_config.ProgressColumn(
                format="%.2f%%", min_value=0.0,
                max_value=float(display["Weight %"].max()) or 1.0,
            ),
            "Risk contrib %":  st.column_config.ProgressColumn(
                format="%.2f%%", min_value=0.0,
                max_value=float(display["Risk contrib %"].max()) or 1.0,
            ),
            "Vol %":           st.column_config.NumberColumn(format="%.2f%%"),
            "Marginal risk":   st.column_config.NumberColumn(format="%.4f"),
        },
    )

    # Flag where Risk contrib >> Weight (over-contribution to variance)
    over = df[df["risk_contrib"] > df["weight"] * 1.4]
    if not over.empty:
        names = ", ".join(over.index)
        st.markdown(
            f'<div style="color:var(--accent); font-size:12px; '
            f'margin-top:8px;">'
            f'⚠ {names} contribute disproportionately to portfolio variance '
            f'relative to their capital weight.'
            '</div>',
            unsafe_allow_html=True,
        )
