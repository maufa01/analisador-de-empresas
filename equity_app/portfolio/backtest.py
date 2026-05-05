"""
Walk-forward backtester.

Splits the price panel into a training window (used to fit weights via
the chosen optimizer) and an out-of-sample window (used to evaluate
those frozen weights). Optionally rebalances inside the OOS window on a
fixed cadence — the default is a single hold-to-end run, which is the
honest read on overfitting.

Returns both the OOS return time series and a benchmark series (typically
the S&P 500, fed in via ``benchmark_returns``) so the page can render
cumulative-return curves and a drawdown comparison.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd

from core.constants import PORTFOLIO_DEFAULTS
from .optimizer import OptimizationResult, max_sharpe, min_vol, risk_parity, equal_weight


_OBJECTIVES: dict[str, Callable[..., OptimizationResult]] = {
    "max_sharpe":   max_sharpe,
    "min_vol":      min_vol,
    "risk_parity":  risk_parity,
    "equal_weight": equal_weight,
}


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class BacktestResult:
    weights_initial: pd.Series
    portfolio_returns: pd.Series
    benchmark_returns: Optional[pd.Series]
    cumulative: pd.DataFrame                # columns: portfolio, benchmark (if any)
    rebalance_dates: list[pd.Timestamp] = field(default_factory=list)
    train_start: Optional[pd.Timestamp] = None
    train_end: Optional[pd.Timestamp] = None
    oos_start: Optional[pd.Timestamp] = None
    oos_end: Optional[pd.Timestamp] = None


# ============================================================
# Internals
# ============================================================
def _to_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna(how="all")


def _train_test_split(
    returns: pd.DataFrame, train_pct: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(returns)
    if n < 30:
        raise ValueError("Need at least 30 return observations to backtest")
    cutoff = max(20, int(n * train_pct))
    return returns.iloc[:cutoff], returns.iloc[cutoff:]


def _portfolio_oos_returns(
    weights: pd.Series, oos_returns: pd.DataFrame
) -> pd.Series:
    """Daily portfolio return assuming buy-and-hold of ``weights``."""
    aligned = oos_returns[weights.index]
    return (aligned * weights.values).sum(axis=1)


# ============================================================
# Public API
# ============================================================
def walk_forward(
    *,
    prices: pd.DataFrame,
    objective: str = "max_sharpe",
    train_pct: float = PORTFOLIO_DEFAULTS["backtest_train_pct"],
    benchmark_prices: Optional[pd.Series] = None,
    optimizer_kwargs: Optional[dict] = None,
) -> BacktestResult:
    """
    Single-cut walk-forward backtest.

    Fit ``objective`` on the first ``train_pct`` of the price panel; hold
    the resulting weights through the OOS tail. Returns both portfolio and
    (optional) benchmark cumulative wealth curves indexed by date.
    """
    if objective not in _OBJECTIVES:
        raise ValueError(f"Unknown objective: {objective}")

    returns = _to_returns(prices)
    train, oos = _train_test_split(returns, train_pct)

    fit = _OBJECTIVES[objective]
    res = fit(train, **(optimizer_kwargs or {}))
    weights = res.weights

    port_oos = _portfolio_oos_returns(weights, oos)
    cum = (1.0 + port_oos).cumprod().rename("portfolio").to_frame()

    bench_oos: Optional[pd.Series] = None
    if benchmark_prices is not None:
        bench_returns = benchmark_prices.pct_change().dropna()
        bench_oos = bench_returns.reindex(port_oos.index).fillna(0.0)
        cum["benchmark"] = (1.0 + bench_oos).cumprod()

    return BacktestResult(
        weights_initial=weights,
        portfolio_returns=port_oos,
        benchmark_returns=bench_oos,
        cumulative=cum,
        rebalance_dates=[oos.index[0]] if len(oos) else [],
        train_start=train.index[0] if len(train) else None,
        train_end=train.index[-1] if len(train) else None,
        oos_start=oos.index[0] if len(oos) else None,
        oos_end=oos.index[-1] if len(oos) else None,
    )


def rolling_rebalance(
    *,
    prices: pd.DataFrame,
    objective: str = "max_sharpe",
    train_window: int = 252,
    rebalance_every: int = 63,            # ~1 quarter
    benchmark_prices: Optional[pd.Series] = None,
    optimizer_kwargs: Optional[dict] = None,
) -> BacktestResult:
    """
    Rolling re-fit: every ``rebalance_every`` periods, refit on the most
    recent ``train_window`` of returns and hold those weights until the
    next rebalance. Useful when the user expects regime shifts.
    """
    if objective not in _OBJECTIVES:
        raise ValueError(f"Unknown objective: {objective}")

    returns = _to_returns(prices)
    if len(returns) <= train_window + 5:
        raise ValueError(
            f"Need > train_window + 5 = {train_window + 5} observations; "
            f"got {len(returns)}"
        )

    fit = _OBJECTIVES[objective]
    portfolio = pd.Series(0.0, index=returns.index[train_window:])
    rebal_dates: list[pd.Timestamp] = []
    initial_weights: Optional[pd.Series] = None
    weights = None

    for i in range(train_window, len(returns)):
        if (i - train_window) % rebalance_every == 0:
            window = returns.iloc[i - train_window:i]
            res = fit(window, **(optimizer_kwargs or {}))
            weights = res.weights
            rebal_dates.append(returns.index[i])
            if initial_weights is None:
                initial_weights = weights
        # Daily portfolio return at i, assuming weights from last refit
        if weights is not None:
            r_today = returns.iloc[i]
            aligned = r_today.reindex(weights.index).fillna(0.0)
            portfolio.iloc[i - train_window] = float((aligned * weights.values).sum())

    cum = (1.0 + portfolio).cumprod().rename("portfolio").to_frame()
    bench_oos: Optional[pd.Series] = None
    if benchmark_prices is not None:
        bench_returns = benchmark_prices.pct_change().dropna()
        bench_oos = bench_returns.reindex(portfolio.index).fillna(0.0)
        cum["benchmark"] = (1.0 + bench_oos).cumprod()

    return BacktestResult(
        weights_initial=initial_weights if initial_weights is not None else pd.Series(dtype=float),
        portfolio_returns=portfolio,
        benchmark_returns=bench_oos,
        cumulative=cum,
        rebalance_dates=rebal_dates,
        train_start=returns.index[0],
        train_end=returns.index[train_window - 1] if train_window <= len(returns) else None,
        oos_start=portfolio.index[0] if len(portfolio) else None,
        oos_end=portfolio.index[-1] if len(portfolio) else None,
    )
