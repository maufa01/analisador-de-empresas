"""
Side-by-side comparison of every supported objective.

Re-runs Max Sharpe / Min Vol / Risk Parity / HRP / Equal Weight on the
same return panel and lays the headline metrics out in a single table
so the user can pick the trade-off that matches their risk tolerance.
Best metric per row is tinted green via the Styler API.
"""
from __future__ import annotations
from typing import Optional

import math
import numpy as np
import pandas as pd
import streamlit as st

from portfolio.optimizer import (
    OptimizationResult,
    max_sharpe, min_vol, risk_parity, equal_weight, hrp,
)
from portfolio.var_calculator import compute_risk_metrics


_OBJECTIVES = ["Max Sharpe", "Min Vol", "Risk Parity", "HRP", "Equal Weight"]


def _run(name: str, returns: pd.DataFrame, kwargs: dict) -> Optional[OptimizationResult]:
    try:
        if name == "Max Sharpe":
            return max_sharpe(returns, **kwargs)
        if name == "Min Vol":
            return min_vol(returns, **kwargs)
        if name == "Risk Parity":
            return risk_parity(returns,
                               max_position=kwargs.get("max_position", 1.0),
                               min_position=1e-6,
                               risk_free=kwargs.get("risk_free", 0.045))
        if name == "HRP":
            return hrp(returns, risk_free=kwargs.get("risk_free", 0.045))
        if name == "Equal Weight":
            return equal_weight(returns, risk_free=kwargs.get("risk_free", 0.045))
    except Exception:
        return None
    return None


def render_strategy_comparison(
    returns: pd.DataFrame,
    *,
    risk_free: float = 0.045,
    max_position: float = 0.30,
    min_position: float = 0.0,
) -> None:
    if returns is None or returns.empty:
        st.info("No return series available.")
        return

    rows: list[dict] = []
    weights_per_strategy: dict[str, pd.Series] = {}

    base_kwargs = {"risk_free": risk_free, "max_position": max_position,
                   "min_position": min_position}

    for name in _OBJECTIVES:
        res = _run(name, returns, base_kwargs)
        if res is None:
            continue
        # OOS-ish stats: just use in-sample portfolio returns from the
        # optimizer's weights. Real backtesting lives in the Backtest tab.
        port_returns = (returns * res.weights).sum(axis=1)
        rm = compute_risk_metrics(port_returns, risk_free_annual=risk_free)
        rows.append({
            "Strategy":      name,
            "Expected ret":  res.expected_return,
            "Volatility":    res.volatility,
            "Sharpe":        res.sharpe,
            "Sortino":       rm.sortino,
            "Max DD":        rm.max_drawdown,
            "VaR 95%":       rm.var_95,
            "Active assets": int((res.weights > 1e-3).sum()),
        })
        weights_per_strategy[name] = res.weights

    if not rows:
        st.warning("Could not compute any strategy comparisons.")
        return

    df = pd.DataFrame(rows).set_index("Strategy")

    # Convert decimals → percent units for display
    for col in ("Expected ret", "Volatility", "Max DD", "VaR 95%"):
        df[col] = df[col] * 100.0

    # Style: highlight best per column
    higher_better = {"Expected ret", "Sharpe", "Sortino"}
    lower_better  = {"Volatility", "Max DD", "VaR 95%"}

    def _color_col(col: pd.Series) -> list[str]:
        clean = col.dropna()
        if clean.empty:
            return [""] * len(col)
        if col.name in higher_better:
            best = clean.max()
        elif col.name in lower_better:
            # Lower magnitude is better (Max DD and VaR are positive numbers
            # representing loss magnitudes via compute_risk_metrics)
            best = clean.min()
        else:
            return [""] * len(col)
        return [
            "background-color: rgba(16,185,129,0.10);"
            if (v == best) else ""
            for v in col
        ]

    styled = df.style.apply(_color_col, axis=0)
    st.dataframe(
        styled,
        use_container_width=True,
        column_config={
            "Expected ret":  st.column_config.NumberColumn(format="%.2f%%"),
            "Volatility":    st.column_config.NumberColumn(format="%.2f%%"),
            "Sharpe":        st.column_config.NumberColumn(format="%.3f"),
            "Sortino":       st.column_config.NumberColumn(format="%.3f"),
            "Max DD":        st.column_config.NumberColumn(format="%.2f%%"),
            "VaR 95%":       st.column_config.NumberColumn(format="%.2f%%"),
            "Active assets": st.column_config.NumberColumn(format="%d"),
        },
    )
