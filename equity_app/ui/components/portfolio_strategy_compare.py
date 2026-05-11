"""Side-by-side comparison of 5 portfolio strategies with "Use this
template" buttons to rebuild the holdings from any strategy's weights.

Strategies computed by ui.components.portfolio_markowitz.compute_strategy_weights.
"""
from __future__ import annotations
from typing import Optional

import math
import numpy as np
import pandas as pd
import streamlit as st

from ui.components.portfolio_markowitz import (
    compute_strategy_weights, compute_strategy_metrics,
)


_STRATEGIES_ORDER = (
    "Current", "Min Variance", "Max Sharpe", "Risk Parity", "Equal Weight",
)


def _format_pct(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v*100:.1f}%"


def _format_metric(v: Optional[float], fmt: str) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return fmt % v


def _build_table(
    strategies: dict[str, Optional[dict[str, float]]],
    tickers: list[str],
    metrics_by_strategy: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Wide table: rows=tickers + 5 summary rows; cols=strategies."""
    rows: list[dict] = []
    for tkr in tickers:
        row = {"Ticker": tkr}
        for name in _STRATEGIES_ORDER:
            w = strategies.get(name)
            row[name] = (w.get(tkr, 0.0) * 100.0) if w else float("nan")
        rows.append(row)
    df = pd.DataFrame(rows).set_index("Ticker")

    # Summary footer rows
    metric_rows = {
        "Expected return %": "expected_return",
        "Volatility %":      "volatility",
        "Sharpe":            "sharpe",
        "Max weight %":      "max_weight",
        "Effective N":       "eff_n",
    }
    summary = {}
    for label, key in metric_rows.items():
        summary[label] = {}
        for name in _STRATEGIES_ORDER:
            m = metrics_by_strategy.get(name, {})
            v = m.get(key)
            if v is None:
                summary[label][name] = float("nan")
            elif key in ("expected_return", "volatility", "max_weight"):
                summary[label][name] = v * 100.0
            else:
                summary[label][name] = v
    df_summary = pd.DataFrame(summary).T
    df_summary.index.name = "Ticker"
    return pd.concat([df, df_summary])


def _apply_template_to_holdings(
    weights: dict[str, float],
    current_prices: dict[str, float],
    total_value: float,
) -> str:
    """Rebuild the holdings textarea text from new weights, allocating
    `total_value` proportionally and using current_prices as both
    target and cost basis."""
    lines: list[str] = []
    for tkr, w in weights.items():
        if w <= 0:
            continue
        price = current_prices.get(tkr)
        if price is None or price <= 0:
            continue
        dollar_amount = total_value * w
        shares = math.floor(dollar_amount / price)
        if shares <= 0:
            continue
        lines.append(f"{tkr},{shares},{price:.2f}")
    return "\n".join(lines)


def render_strategy_compare(
    returns: pd.DataFrame,
    current_weights: dict[str, float],
    current_prices: dict[str, float],
) -> None:
    if returns is None or returns.empty:
        st.info("Strategy comparison requires daily returns history.")
        return
    if not current_weights:
        st.info("Strategy comparison needs at least 2 holdings.")
        return

    tickers_in_returns = [t for t in current_weights if t in returns.columns]
    if len(tickers_in_returns) < 2:
        st.info("Need 2+ holdings with overlapping price history.")
        return

    strategies = compute_strategy_weights(returns, current_weights)
    if not strategies:
        st.info("Could not compute strategies (insufficient data).")
        return

    # Per-strategy metrics
    metrics_by_strategy: dict[str, dict[str, float]] = {}
    for name in _STRATEGIES_ORDER:
        w = strategies.get(name)
        if w is None:
            metrics_by_strategy[name] = {}
            continue
        metrics_by_strategy[name] = compute_strategy_metrics(returns, w)

    tickers = list(current_weights.keys())
    df = _build_table(strategies, tickers, metrics_by_strategy)

    # Style: column gradient (per col, green=best, copper=worst)
    palette = ["#1F2937", "#274234", "#3F6F47", "#7F9D5C", "#C9A14A"]
    failed_cols = [name for name in _STRATEGIES_ORDER if strategies.get(name) is None]

    def _color_col(s: pd.Series) -> list[str]:
        # s indexed by Ticker + 5 summary rows; only color ticker rows
        vals = s.iloc[:len(tickers)].astype(float)
        if vals.dropna().empty:
            return [""] * len(s)
        vmin = float(np.nanmin(vals)) if not vals.dropna().empty else 0.0
        vmax = float(np.nanmax(vals)) if not vals.dropna().empty else 1.0
        if vmax <= vmin:
            return [""] * len(s)
        styles: list[str] = []
        for i, v in enumerate(s):
            if i >= len(tickers) or pd.isna(v):
                styles.append("")
                continue
            t = (v - vmin) / (vmax - vmin)
            idx = min(int(t * (len(palette) - 1)), len(palette) - 1)
            styles.append(f"background-color: {palette[idx]};")
        return styles

    styled = df.style.format(precision=2, na_rep="—").apply(
        _color_col, axis=0, subset=list(_STRATEGIES_ORDER)
    )
    st.dataframe(styled, use_container_width=True)

    if failed_cols:
        st.caption(
            f"Optimization did not converge: {', '.join(failed_cols)}. "
            "Those columns show '—' for all rows."
        )

    # ---- "Use this template" buttons ----
    st.markdown(
        '<div style="margin-top:10px;"></div>', unsafe_allow_html=True,
    )
    total_value = sum(current_prices.get(t, 0.0)
                       * (current_weights.get(t, 0.0))
                       for t in current_weights) or 1.0
    # If `current_weights` represents weights (decimals), total_value
    # above is small; we want the REAL total portfolio $ — pull it from
    # session_state if set, else fall back to sum of (shares * price)
    real_total = st.session_state.get("portfolio_total_value", None)
    if real_total and real_total > 0:
        total_value = float(real_total)

    cols = st.columns(len(_STRATEGIES_ORDER))
    for i, name in enumerate(_STRATEGIES_ORDER):
        w = strategies.get(name)
        disabled = (w is None) or (name == "Current")
        btn = cols[i].button(
            f"Use {name}",
            key=f"portfolio_use_strategy_{name.replace(' ', '_')}",
            disabled=disabled,
            help=("Already active" if name == "Current"
                  else ("Optimization failed" if w is None
                        else f"Rebuild holdings with {name} weights "
                             "applied to current portfolio $.")),
            use_container_width=True,
        )
        if btn and w is not None and name != "Current":
            new_text = _apply_template_to_holdings(w, current_prices, total_value)
            if new_text:
                st.session_state["portfolio_holdings_text"] = new_text
                # Force the Raw text mode so the user sees the result
                st.session_state["portfolio_input_mode"] = "Raw text"
                st.rerun()

    st.caption(
        "Strategies are computed from trailing daily returns. Min "
        "Variance / Max Sharpe optimize for stated objectives but are "
        "sensitive to lookback window. Risk Parity and Equal Weight "
        "are robust alternatives that don't require expected-return "
        "estimates."
    )
