"""Educational mean-variance frontier — random portfolios cloud + 5 named
strategies (Current, Min Var, Max Sharpe, Risk Parity, Equal Weight).

NOT a recommendation engine. The disclaimer at the top spells out why
mean-variance is sensitive to lookback window and produces corner
solutions in small portfolios.
"""
from __future__ import annotations
from typing import Optional
import logging
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

log = logging.getLogger(__name__)


# ============================================================
# Strategy computations
# ============================================================
def _portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray
                     ) -> tuple[float, float, float]:
    """(ret, vol, sharpe). Risk-free assumed 0 — keeps comparison clean."""
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
    sharpe = (ret / vol) if vol > 0 else 0.0
    return ret, vol, sharpe


def _min_variance(mu: np.ndarray, cov: np.ndarray) -> Optional[np.ndarray]:
    try:
        from scipy.optimize import minimize
        n = len(mu)
        x0 = np.full(n, 1.0 / n)
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bnds = [(0.0, 1.0)] * n
        res = minimize(lambda w: w @ cov @ w, x0,
                       method="SLSQP", bounds=bnds, constraints=cons,
                       options={"maxiter": 300, "ftol": 1e-9})
        return res.x if res.success else None
    except Exception as e:
        log.warning("Min-var optimisation failed: %s", e)
        return None


def _max_sharpe(mu: np.ndarray, cov: np.ndarray) -> Optional[np.ndarray]:
    try:
        from scipy.optimize import minimize
        n = len(mu)
        x0 = np.full(n, 1.0 / n)
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bnds = [(0.0, 1.0)] * n

        def neg_sharpe(w: np.ndarray) -> float:
            ret = w @ mu
            vol = np.sqrt(max(w @ cov @ w, 1e-12))
            return -ret / vol

        res = minimize(neg_sharpe, x0,
                       method="SLSQP", bounds=bnds, constraints=cons,
                       options={"maxiter": 300, "ftol": 1e-9})
        return res.x if res.success else None
    except Exception as e:
        log.warning("Max-Sharpe optimisation failed: %s", e)
        return None


def _risk_parity(cov: np.ndarray, *, max_iter: int = 500,
                 tol: float = 1e-6) -> Optional[np.ndarray]:
    """Iterative coordinate-style RP: each w_i scaled by target_risk /
    its MCTR until convergence. Simple and converges for well-conditioned
    cov matrices."""
    try:
        n = cov.shape[0]
        if n == 1:
            return np.array([1.0])
        w = np.full(n, 1.0 / n)
        target_rc = 1.0 / n  # equal contribution
        for _ in range(max_iter):
            port_var = float(w @ cov @ w)
            if port_var <= 0:
                return None
            port_vol = np.sqrt(port_var)
            mctr = (cov @ w) / port_vol            # marginal contrib
            rc = w * mctr / port_vol               # % contribution
            # Newton-like update: scale by (target / current_rc)
            adjust = (target_rc / np.maximum(rc, 1e-12)) ** 0.5
            new_w = w * adjust
            new_w = np.maximum(new_w, 0.0)
            new_w /= new_w.sum()
            if np.max(np.abs(new_w - w)) < tol:
                return new_w
            w = new_w
        return w
    except Exception as e:
        log.warning("Risk-parity failed: %s", e)
        return None


# ============================================================
# Public helpers — reusable by other components (Compare tab, KPI cards)
# ============================================================
def compute_strategy_weights(
    returns: pd.DataFrame,
    current_weights: dict[str, float],
) -> dict[str, Optional[dict[str, float]]]:
    """Return {strategy_name: {ticker: weight} | None}. None means the
    optimisation failed to converge — caller decides how to render
    (skip column, show '—', etc.)."""
    if returns is None or returns.empty or not current_weights:
        return {}
    tickers = [t for t in current_weights if t in returns.columns]
    if len(tickers) < 2:
        return {}
    rets = returns[tickers].dropna(how="any")
    if len(rets) < 60:
        return {}

    mu = (rets.mean() * 252.0).values
    cov = (rets.cov() * 252.0).values

    raw = np.array([current_weights[t] for t in tickers], dtype=float)
    w_current = (raw / raw.sum()) if raw.sum() > 0 else np.full(len(tickers), 1 / len(tickers))
    n = len(tickers)
    w_eq = np.full(n, 1.0 / n)
    w_minv = _min_variance(mu, cov)
    w_maxs = _max_sharpe(mu, cov)
    w_rp = _risk_parity(cov)

    def _to_dict(arr: Optional[np.ndarray]) -> Optional[dict[str, float]]:
        if arr is None:
            return None
        return {tickers[i]: float(arr[i]) for i in range(len(tickers))}

    return {
        "Current":      _to_dict(w_current),
        "Min Variance": _to_dict(w_minv),
        "Max Sharpe":   _to_dict(w_maxs),
        "Risk Parity":  _to_dict(w_rp),
        "Equal Weight": _to_dict(w_eq),
    }


def compute_strategy_metrics(
    returns: pd.DataFrame,
    weights: dict[str, float],
) -> dict[str, float]:
    """Annualised expected_return, volatility, sharpe, max_weight, eff_n
    for a given (returns, weights) pair. Empty dict on degenerate input."""
    if returns is None or returns.empty or not weights:
        return {}
    tickers = [t for t in weights if t in returns.columns]
    if not tickers:
        return {}
    rets = returns[tickers].dropna(how="any")
    if rets.empty:
        return {}
    w = np.array([weights[t] for t in tickers], dtype=float)
    if w.sum() <= 0:
        return {}
    w = w / w.sum()
    mu = (rets.mean() * 252.0).values
    cov = (rets.cov() * 252.0).values
    exp_ret = float(w @ mu)
    var = float(w @ cov @ w)
    vol = math.sqrt(max(var, 0.0))
    sharpe = (exp_ret / vol) if vol > 0 else 0.0
    max_w = float(max(w))
    hhi = float(np.sum(w * w))
    eff_n = (1.0 / hhi) if hhi > 0 else float("nan")
    return {
        "expected_return": exp_ret,
        "volatility":      vol,
        "sharpe":          sharpe,
        "max_weight":      max_w,
        "eff_n":           eff_n,
    }


# ============================================================
# Public renderer
# ============================================================
def render_markowitz_frontier(
    returns: pd.DataFrame,
    weights: dict[str, float],
    *,
    n_random_portfolios: int = 8000,
) -> None:
    if returns is None or returns.empty:
        st.info("Markowitz needs returns data.")
        return

    # Align tickers
    tickers = [t for t in weights if t in returns.columns]
    if len(tickers) < 2:
        st.info("Markowitz needs 2+ holdings with overlapping price history.")
        return
    rets = returns[tickers].dropna(how="any")
    if len(rets) < 60:
        st.info("Need at least ~3 months of overlapping returns.")
        return

    st.warning(
        "Mean-variance optimisation uses **trailing returns** as the "
        "expected-return input. This is highly sensitive to the lookback "
        "window and prone to corner solutions in small portfolios. Treat "
        "this as a visualisation of tradeoffs, **NOT a portfolio "
        "recommendation**. The robust alternatives (Inverse Vol, Risk "
        "Parity, Equal Weight) shown alongside are what professionals "
        "typically use in practice."
    )

    # Annualised stats
    mu = (rets.mean() * 252.0).reindex(tickers).values
    cov = (rets.cov() * 252.0).loc[tickers, tickers].values

    # Normalised current weights
    raw = np.array([weights[t] for t in tickers], dtype=float)
    w_current = raw / raw.sum() if raw.sum() > 0 else np.full(len(tickers), 1/len(tickers))

    # ---- Random portfolios cloud (Dirichlet) ----
    rng = np.random.default_rng(seed=42)
    rand_w = rng.dirichlet(np.ones(len(tickers)), size=n_random_portfolios)
    rand_ret = rand_w @ mu
    rand_var = np.einsum("ij,jk,ik->i", rand_w, cov, rand_w)
    rand_vol = np.sqrt(np.maximum(rand_var, 0.0))

    # ---- Named strategies ----
    n = len(tickers)
    strategies: dict[str, np.ndarray] = {
        "Current": w_current,
        "Equal Weight": np.full(n, 1.0 / n),
    }
    w_minv = _min_variance(mu, cov)
    if w_minv is not None:
        strategies["Min Variance"] = w_minv
    w_maxs = _max_sharpe(mu, cov)
    if w_maxs is not None:
        strategies["Max Sharpe"] = w_maxs
    w_rp = _risk_parity(cov)
    if w_rp is not None:
        strategies["Risk Parity"] = w_rp

    # ---- Scatter plot ----
    palette = {
        "Current":      "#C9A14A",   # gold
        "Min Variance": "#2EC4B6",   # teal
        "Max Sharpe":   "#E63946",   # coral
        "Risk Parity":  "#3B82F6",   # blue
        "Equal Weight": "#6E7B8B",   # gray
    }
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rand_vol * 100.0, y=rand_ret * 100.0,
        mode="markers",
        marker=dict(size=3, color="rgba(255,255,255,0.12)", showscale=False),
        name="Random portfolios",
        hoverinfo="skip", showlegend=False,
    ))
    for name, w in strategies.items():
        ret, vol, sharpe = _portfolio_stats(w, mu, cov)
        hover = "<br>".join(
            f"{tickers[i]}: {w[i]*100:.1f}%"
            for i in range(len(tickers)) if w[i] > 1e-4
        )
        fig.add_trace(go.Scatter(
            x=[vol * 100.0], y=[ret * 100.0],
            mode="markers+text",
            text=[name], textposition="top center",
            textfont=dict(size=11, color=palette.get(name, "#999")),
            marker=dict(size=12, color=palette.get(name, "#999"),
                        line=dict(color="rgba(0,0,0,0)", width=0)),
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>Return %{{y:.1f}}%<br>Vol %{{x:.1f}}%"
                f"<br>Sharpe {sharpe:.2f}<br><br>{hover}<extra></extra>"
            ),
            showlegend=False,
        ))
    fig.update_layout(
        height=420,
        margin=dict(l=50, r=20, t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=11,
                  color="rgba(255,255,255,0.85)"),
        xaxis=dict(title="Annualised volatility (%)",
                   showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(size=10, color="rgba(255,255,255,0.55)"),
                   color="rgba(255,255,255,0.85)"),
        yaxis=dict(title="Annualised return (%)",
                   showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   zeroline=True, zerolinecolor="rgba(255,255,255,0.15)",
                   tickfont=dict(size=10, color="rgba(255,255,255,0.55)"),
                   color="rgba(255,255,255,0.85)"),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Comparison table ----
    rows = []
    for tkr in tickers:
        row = {"Ticker": tkr}
        for name, w in strategies.items():
            row[name] = float(w[tickers.index(tkr)]) * 100.0
        rows.append(row)
    df = pd.DataFrame(rows).set_index("Ticker")

    # Sharpe / Δ vs Current footer rows
    sharpe_row = {"Ticker": "Sharpe ratio"}
    for name, w in strategies.items():
        _, _, sharpe = _portfolio_stats(w, mu, cov)
        sharpe_row[name] = sharpe
    sharpe_df = pd.DataFrame([sharpe_row]).set_index("Ticker")

    cfg = {
        name: st.column_config.NumberColumn(format="%.1f%%")
        for name in strategies
    }
    st.markdown("**Strategy weights**")
    st.dataframe(df.round(2), use_container_width=True, column_config=cfg)
    st.markdown("**Sharpe ratio per strategy**")
    st.dataframe(sharpe_df.round(2), use_container_width=True,
                 column_config={name: st.column_config.NumberColumn(format="%.2f")
                                for name in strategies})

    # ---- Sensitivity panel (lookback selector for Max Sharpe) ----
    st.markdown("---")
    st.markdown("**Max-Sharpe weights across lookback windows**")
    st.caption(
        "Re-runs the Max-Sharpe optimisation on different historical "
        "windows of the same returns dataframe. Watch how the weights "
        "shift — that's the instability of mean-variance laid bare."
    )

    windows_days = {"1y": 252, "3y": 756, "5y": 1260, "10y": 2520}
    sens_rows = []
    for label, days in windows_days.items():
        sub = rets.tail(days)
        if len(sub) < 60:
            continue
        mu_sub = (sub.mean() * 252.0).values
        cov_sub = (sub.cov() * 252.0).values
        w_sens = _max_sharpe(mu_sub, cov_sub)
        if w_sens is None:
            continue
        row = {"Window": label}
        for i, tkr in enumerate(tickers):
            row[tkr] = float(w_sens[i]) * 100.0
        _, _, sharpe = _portfolio_stats(w_sens, mu_sub, cov_sub)
        row["Sharpe"] = sharpe
        sens_rows.append(row)
    if sens_rows:
        sens_df = pd.DataFrame(sens_rows).set_index("Window")
        cfg2 = {tkr: st.column_config.NumberColumn(format="%.1f%%")
                for tkr in tickers}
        cfg2["Sharpe"] = st.column_config.NumberColumn(format="%.2f")
        st.dataframe(sens_df.round(2), use_container_width=True,
                     column_config=cfg2)
        st.info(
            "Notice how Max-Sharpe weights shift across lookback windows. "
            "The 'optimal' portfolio is a function of which past you pick. "
            "Robust strategies like Risk Parity don't have this instability "
            "because they don't require expected returns as input."
        )
