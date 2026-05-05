"""
Mean-variance and risk-parity portfolio optimization.

Public objectives
-----------------
- ``max_sharpe`` — maximises the (annualized) Sharpe ratio
- ``min_vol``    — global minimum-variance portfolio
- ``risk_parity`` — equal risk contribution (ERC); uses the marginal-risk
  algorithm from Maillard, Roncalli & Teiletche (2010)
- ``equal_weight`` — naive 1/N benchmark
- ``efficient_frontier`` — sweeps target returns to draw the frontier

All long-only by default and constraint-aware via
``portfolio.constraints.build_constraints``. Inputs accept either log-
or simple-return DataFrames (``log_returns=True`` toggles); covariance
is shrunk via Ledoit-Wolf unless an explicit one is passed.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from core.constants import PORTFOLIO_DEFAULTS
from .constraints import build_constraints
from .shrinkage import ledoit_wolf
from .hrp import hrp_weights
from .black_litterman import black_litterman_returns, View


Objective = Literal[
    "max_sharpe", "min_vol", "risk_parity", "equal_weight",
    "hrp", "black_litterman",
]
TRADING_DAYS = PORTFOLIO_DEFAULTS["trading_days"]


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class OptimizationResult:
    weights: pd.Series
    expected_return: float
    volatility: float
    sharpe: float
    objective: str
    n_iterations: int
    converged: bool
    message: str = ""


# ============================================================
# Inputs
# ============================================================
def _expected_returns(returns: pd.DataFrame, *, trading_days: int) -> pd.Series:
    """Sample mean × trading days."""
    return returns.mean() * trading_days


def _ensure_cov(
    returns: pd.DataFrame,
    cov: Optional[pd.DataFrame],
    trading_days: int,
) -> pd.DataFrame:
    if cov is not None:
        return cov.reindex(index=returns.columns, columns=returns.columns)
    return ledoit_wolf(returns, annualize=trading_days).covariance


def _portfolio_stats(
    weights: np.ndarray,
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free: float,
) -> tuple[float, float, float]:
    ret = float(weights @ mu)
    vol = float(np.sqrt(weights @ cov @ weights))
    sharpe = (ret - risk_free) / vol if vol > 0 else 0.0
    return ret, vol, sharpe


# ============================================================
# Single-objective optimizers
# ============================================================
def _solve(
    *,
    objective_fn,
    n: int,
    bounds: list,
    cons: list,
    x0: Optional[np.ndarray] = None,
    options: Optional[dict] = None,
) -> tuple[np.ndarray, "object"]:
    if x0 is None:
        x0 = np.full(n, 1.0 / n)
    opts = {"maxiter": 200, "ftol": 1e-9}
    if options:
        opts.update(options)
    res = minimize(
        objective_fn, x0, method="SLSQP",
        bounds=bounds, constraints=cons, options=opts,
    )
    return res.x, res


def max_sharpe(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = 0.0,
    sector_map: Optional[dict[str, str]] = None,
    sector_caps: Optional[dict[str, float]] = None,
) -> OptimizationResult:
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)

    bounds, cons = build_constraints(
        tickers=tickers,
        sector_map=sector_map, sector_caps=sector_caps,
        max_position=max_position, min_position=min_position,
    )

    mu_arr, cov_arr = mu.values, sigma.values
    def neg_sharpe(w):
        ret, vol, _ = _portfolio_stats(w, mu_arr, cov_arr, risk_free)
        return -((ret - risk_free) / vol) if vol > 0 else 1e6

    w, res = _solve(objective_fn=neg_sharpe, n=len(tickers), bounds=bounds, cons=cons)
    ret, vol, sh = _portfolio_stats(w, mu_arr, cov_arr, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="max_sharpe",
        n_iterations=int(res.nit),
        converged=bool(res.success),
        message=str(res.message),
    )


def min_vol(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = 0.0,
    sector_map: Optional[dict[str, str]] = None,
    sector_caps: Optional[dict[str, float]] = None,
) -> OptimizationResult:
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)

    bounds, cons = build_constraints(
        tickers=tickers,
        sector_map=sector_map, sector_caps=sector_caps,
        max_position=max_position, min_position=min_position,
    )
    cov_arr = sigma.values
    def variance(w):
        return float(w @ cov_arr @ w)

    w, res = _solve(objective_fn=variance, n=len(tickers), bounds=bounds, cons=cons)
    ret, vol, sh = _portfolio_stats(w, mu.values, cov_arr, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="min_vol",
        n_iterations=int(res.nit),
        converged=bool(res.success),
        message=str(res.message),
    )


def risk_parity(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = 1e-6,
) -> OptimizationResult:
    """
    Equal Risk Contribution (ERC) portfolio — every asset contributes
    the same fraction to total portfolio variance.

    Long-only by construction (the formulation requires positive weights).
    Sector caps deliberately not exposed: ERC's defining property is broken
    under group constraints.
    """
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)
    n = len(tickers)
    cov_arr = sigma.values

    bounds, cons = build_constraints(
        tickers=tickers, max_position=max_position, min_position=min_position,
    )
    target = 1.0 / n

    def loss(w):
        port_var = float(w @ cov_arr @ w)
        if port_var <= 0:
            return 1e6
        rc = w * (cov_arr @ w) / port_var          # risk contribution share
        return float(np.sum((rc - target) ** 2))

    w, res = _solve(
        objective_fn=loss, n=n, bounds=bounds, cons=cons,
        options={"maxiter": 500},
    )
    ret, vol, sh = _portfolio_stats(w, mu.values, cov_arr, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="risk_parity",
        n_iterations=int(res.nit),
        converged=bool(res.success),
        message=str(res.message),
    )


def equal_weight(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
) -> OptimizationResult:
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)
    n = len(tickers)
    w = np.full(n, 1.0 / n)
    ret, vol, sh = _portfolio_stats(w, mu.values, sigma.values, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="equal_weight",
        n_iterations=0,
        converged=True,
    )


# ============================================================
# Efficient frontier
# ============================================================
def efficient_frontier(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    n_points: int = 30,
    trading_days: int = TRADING_DAYS,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = 0.0,
) -> pd.DataFrame:
    """
    Sweep target returns from min(μ) to max(μ) and minimise variance for
    each. Failed targets are dropped. Output columns: return, vol, sharpe.
    """
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)
    n = len(tickers)
    cov_arr = sigma.values
    mu_arr = mu.values

    # We need the achievable return range under the bounds — so fall back
    # to (min, max) of expected returns across single-asset portfolios.
    rf = PORTFOLIO_DEFAULTS["risk_free_rate"]

    # Lower bound of feasible returns: min-vol return; upper bound: max(mu).
    try:
        lo_ret = min_vol(
            returns, cov=sigma, max_position=max_position, min_position=min_position,
            trading_days=trading_days,
        ).expected_return
    except Exception:
        lo_ret = float(mu.min())
    hi_ret = float(mu.max())
    if hi_ret <= lo_ret:
        return pd.DataFrame(columns=["return", "volatility", "sharpe"])

    targets = np.linspace(lo_ret, hi_ret, n_points)
    rows = []
    for t in targets:
        bounds, cons = build_constraints(
            tickers=tickers, max_position=max_position, min_position=min_position,
            target_return=float(t), expected_returns=mu_arr,
        )
        w, res = _solve(
            objective_fn=lambda w: float(w @ cov_arr @ w),
            n=n, bounds=bounds, cons=cons,
        )
        if not res.success:
            continue
        ret, vol, sh = _portfolio_stats(w, mu_arr, cov_arr, rf)
        rows.append({"return": ret, "volatility": vol, "sharpe": sh})

    return pd.DataFrame(rows)


# ============================================================
# HRP (Hierarchical Risk Parity)
# ============================================================
def hrp(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
) -> OptimizationResult:
    """
    Allocate via López de Prado's HRP. Long-only by construction.

    Constraints (max_position / sector caps) aren't applied — HRP's
    defining property is robustness through the cluster ordering, not
    bound respect. Use max_sharpe with sector caps if you need those.
    """
    mu = _expected_returns(returns, trading_days=trading_days)
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)

    w_series = hrp_weights(returns)
    w = w_series.reindex(tickers).fillna(0.0).values

    ret, vol, sh = _portfolio_stats(w, mu.values, sigma.values, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="hrp",
        n_iterations=0, converged=True,
    )


# ============================================================
# Black-Litterman → Max Sharpe
# ============================================================
def black_litterman(
    returns: pd.DataFrame,
    *,
    market_weights: pd.Series,
    views: Optional[list[View]] = None,
    cov: Optional[pd.DataFrame] = None,
    risk_aversion: float = 2.5,
    tau: float = 0.05,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = TRADING_DAYS,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = 0.0,
) -> OptimizationResult:
    """
    Mean-variance with Black-Litterman posterior expected returns.

    With ``views=None`` reduces to max-Sharpe over the equilibrium
    implied returns ``Π``. Pass ``View(asset_long=…, magnitude=…)``
    for absolute / relative tilts.
    """
    sigma = _ensure_cov(returns, cov, trading_days)
    tickers = list(returns.columns)

    bl_mu = black_litterman_returns(
        cov=sigma, market_weights=market_weights, views=views,
        risk_aversion=risk_aversion, tau=tau,
    ).reindex(tickers)

    bounds, cons = build_constraints(
        tickers=tickers, max_position=max_position, min_position=min_position,
    )
    mu_arr, cov_arr = bl_mu.values, sigma.values

    def neg_sharpe(w):
        ret, vol, _ = _portfolio_stats(w, mu_arr, cov_arr, risk_free)
        return -((ret - risk_free) / vol) if vol > 0 else 1e6

    w, res = _solve(objective_fn=neg_sharpe, n=len(tickers),
                    bounds=bounds, cons=cons)
    ret, vol, sh = _portfolio_stats(w, mu_arr, cov_arr, risk_free)
    return OptimizationResult(
        weights=pd.Series(w, index=tickers, name="weight"),
        expected_return=ret, volatility=vol, sharpe=sh,
        objective="black_litterman",
        n_iterations=int(res.nit),
        converged=bool(res.success),
        message=str(res.message),
    )


# ============================================================
# Dispatcher
# ============================================================
def optimize(
    returns: pd.DataFrame,
    objective: Objective = "max_sharpe",
    **kwargs,
) -> OptimizationResult:
    fn = {
        "max_sharpe":      max_sharpe,
        "min_vol":         min_vol,
        "risk_parity":     risk_parity,
        "equal_weight":    equal_weight,
        "hrp":             hrp,
        "black_litterman": black_litterman,
    }.get(objective)
    if fn is None:
        raise ValueError(f"Unknown objective: {objective}")
    if objective == "equal_weight":
        # equal_weight has a narrower kwarg surface
        keep = {k: v for k, v in kwargs.items()
                if k in {"cov", "risk_free", "trading_days"}}
        return fn(returns, **keep)
    if objective == "hrp":
        keep = {k: v for k, v in kwargs.items()
                if k in {"cov", "risk_free", "trading_days"}}
        return fn(returns, **keep)
    return fn(returns, **kwargs)
