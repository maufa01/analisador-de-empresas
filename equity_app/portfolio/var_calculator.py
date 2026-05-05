"""
Risk metrics: VaR, CVaR, drawdown, Sharpe, Sortino, Calmar.

Conventions
-----------
- ``returns`` is a 1-D pandas Series of *periodic* returns (typically
  daily). Annualization uses ``trading_days`` (252 by default).
- VaR / CVaR are reported as **positive** percentages by default —
  i.e. a 5% VaR means the loss is 5% in the tail. Pass
  ``signed=True`` to keep the signs.
- Sharpe and Sortino expect ``risk_free`` in the same period as
  ``returns``; use ``annual_risk_free / trading_days`` for daily.

Three VaR methods are provided:
- ``historical`` — empirical quantile of past returns
- ``parametric`` — assumes Gaussian, uses mean/std and the inverse normal
- ``monte_carlo`` — bootstrap of historical returns
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

from core.constants import PORTFOLIO_DEFAULTS


VaRMethod = Literal["historical", "parametric", "monte_carlo"]


# ============================================================
# Aggregate dataclass
# ============================================================
@dataclass
class RiskMetrics:
    annual_return: float
    annual_volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float                 # positive number, e.g. 0.32 for -32%
    var_95: float
    cvar_95: float
    skewness: float
    kurtosis: float
    n_observations: int


# ============================================================
# Building blocks
# ============================================================
def annualized_return(returns: pd.Series, trading_days: int = 252) -> float:
    r = returns.dropna()
    if r.empty:
        return float("nan")
    return float((1.0 + r).prod() ** (trading_days / len(r)) - 1.0)


def annualized_volatility(returns: pd.Series, trading_days: int = 252) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1) * np.sqrt(trading_days))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_annual: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = 252,
) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    rf = risk_free_annual / trading_days
    excess = r - rf
    sd = excess.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(trading_days))


def sortino_ratio(
    returns: pd.Series,
    risk_free_annual: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    trading_days: int = 252,
) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    rf = risk_free_annual / trading_days
    excess = r - rf
    downside = excess[excess < 0]
    if downside.empty:
        return float("inf")
    dd_std = downside.std(ddof=1)
    if dd_std == 0:
        return float("nan")
    return float(excess.mean() / dd_std * np.sqrt(trading_days))


# ============================================================
# Drawdown
# ============================================================
def drawdown_series(returns: pd.Series) -> pd.Series:
    """
    Cumulative drawdown series: 0 at the running peak, negative below.
    """
    r = returns.dropna()
    if r.empty:
        return pd.Series(dtype=float)
    wealth = (1.0 + r).cumprod()
    peak = wealth.cummax()
    return wealth / peak - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Worst drawdown as a positive number (e.g. 0.42 for a -42% trough)."""
    dd = drawdown_series(returns)
    if dd.empty:
        return float("nan")
    return float(-dd.min())


def calmar_ratio(returns: pd.Series, trading_days: int = 252) -> float:
    mdd = max_drawdown(returns)
    if not np.isfinite(mdd) or mdd <= 0:
        return float("nan")
    return float(annualized_return(returns, trading_days) / mdd)


# ============================================================
# VaR / CVaR
# ============================================================
def value_at_risk(
    returns: pd.Series,
    *,
    confidence: float = 0.95,
    method: VaRMethod = "historical",
    n_simulations: int = 10_000,
    signed: bool = False,
    seed: Optional[int] = None,
) -> float:
    """
    One-period VaR at ``confidence`` (0.95 ⇒ 95% confidence).

    Returned as a positive number (loss magnitude) by default.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")

    alpha = 1.0 - confidence
    if method == "historical":
        q = float(np.quantile(r.values, alpha))
    elif method == "parametric":
        from scipy.stats import norm  # type: ignore
        z = float(norm.ppf(alpha))
        q = float(r.mean() + z * r.std(ddof=1))
    elif method == "monte_carlo":
        rng = np.random.default_rng(seed)
        sample = rng.choice(r.values, size=n_simulations, replace=True)
        q = float(np.quantile(sample, alpha))
    else:
        raise ValueError(f"Unknown VaR method: {method}")

    return q if signed else -q


def conditional_var(
    returns: pd.Series,
    *,
    confidence: float = 0.95,
    signed: bool = False,
) -> float:
    """
    Expected Shortfall (CVaR): mean of returns below the VaR threshold.

    Always uses the historical method — for parametric / MC bootstraps
    fall back to ``value_at_risk`` first.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    threshold = float(np.quantile(r.values, 1.0 - confidence))
    tail = r[r <= threshold]
    if tail.empty:
        return float("nan")
    mean_loss = float(tail.mean())
    return mean_loss if signed else -mean_loss


# ============================================================
# Aggregate API
# ============================================================
def compute_risk_metrics(
    returns: pd.Series,
    *,
    risk_free_annual: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    confidence: float = PORTFOLIO_DEFAULTS["var_confidence"],
    trading_days: int = PORTFOLIO_DEFAULTS["trading_days"],
) -> RiskMetrics:
    r = returns.dropna()
    return RiskMetrics(
        annual_return=annualized_return(r, trading_days),
        annual_volatility=annualized_volatility(r, trading_days),
        sharpe=sharpe_ratio(r, risk_free_annual, trading_days),
        sortino=sortino_ratio(r, risk_free_annual, trading_days),
        calmar=calmar_ratio(r, trading_days),
        max_drawdown=max_drawdown(r),
        var_95=value_at_risk(r, confidence=confidence, method="historical"),
        cvar_95=conditional_var(r, confidence=confidence),
        skewness=float(r.skew()) if len(r) > 2 else float("nan"),
        kurtosis=float(r.kurtosis()) if len(r) > 3 else float("nan"),
        n_observations=int(len(r)),
    )
