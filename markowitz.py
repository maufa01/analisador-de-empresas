"""
Optimización media-varianza (Markowitz).

- Retornos esperados: media de log-retornos diarios anualizada (* 252)
- Covarianza: matriz de cov de log-retornos anualizada
- Frontera eficiente: minimizar varianza sujeto a target return + sum(w)=1
- Max Sharpe: minimizar -(ret - rf) / vol
- Min Vol: minimizar varianza sin target return

Soporta long-only (default) y long/short.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from config import PORTFOLIO_DEFAULTS

DAYS = PORTFOLIO_DEFAULTS["trading_days"]


def expected_returns(prices: pd.DataFrame) -> pd.Series:
    """Retornos esperados anualizados (log-retornos)."""
    log_r = np.log(prices / prices.shift(1)).dropna()
    return log_r.mean() * DAYS


def covariance_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    log_r = np.log(prices / prices.shift(1)).dropna()
    return log_r.cov() * DAYS


def portfolio_perf(
    weights: np.ndarray,
    mu: np.ndarray,
    cov: np.ndarray,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
) -> tuple[float, float, float]:
    """Retorno, vol, Sharpe del portfolio."""
    w = np.asarray(weights, dtype=float)
    ret = float(w @ mu)
    vol = float(np.sqrt(w @ cov @ w))
    sharpe = (ret - risk_free) / vol if vol > 0 else 0.0
    return ret, vol, sharpe


def _bounds(n: int, allow_short: bool):
    return [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n


def optimize_max_sharpe(
    mu: pd.Series,
    cov: pd.DataFrame,
    risk_free: float = PORTFOLIO_DEFAULTS["risk_free_rate"],
    allow_short: bool = False,
) -> dict:
    """Encuentra el portfolio que maximiza Sharpe."""
    n = len(mu)
    x0 = np.repeat(1 / n, n)
    bounds = _bounds(n, allow_short)
    cons = {"type": "eq", "fun": lambda w: w.sum() - 1}
    
    def neg_sharpe(w):
        return -portfolio_perf(w, mu.values, cov.values, risk_free)[2]
    
    res = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=cons)
    if not res.success:
        raise RuntimeError(f"Max Sharpe falló: {res.message}")
    
    w = pd.Series(res.x, index=mu.index, name="weight").round(4)
    ret, vol, sh = portfolio_perf(res.x, mu.values, cov.values, risk_free)
    return {"weights": w, "return": ret, "volatility": vol, "sharpe": sh}


def optimize_min_vol(
    mu: pd.Series,
    cov: pd.DataFrame,
    allow_short: bool = False,
) -> dict:
    """Portfolio de mínima varianza global."""
    n = len(mu)
    x0 = np.repeat(1 / n, n)
    bounds = _bounds(n, allow_short)
    cons = {"type": "eq", "fun": lambda w: w.sum() - 1}
    
    def vol_fn(w):
        return np.sqrt(w @ cov.values @ w)
    
    res = minimize(vol_fn, x0, method="SLSQP", bounds=bounds, constraints=cons)
    if not res.success:
        raise RuntimeError(f"Min Vol falló: {res.message}")
    
    w = pd.Series(res.x, index=mu.index, name="weight").round(4)
    ret, vol, sh = portfolio_perf(res.x, mu.values, cov.values)
    return {"weights": w, "return": ret, "volatility": vol, "sharpe": sh}


def efficient_frontier(
    mu: pd.Series,
    cov: pd.DataFrame,
    n_points: int = 50,
    allow_short: bool = False,
) -> pd.DataFrame:
    """
    Construye n puntos de la frontera eficiente.
    Para cada target_return en [min(mu), max(mu)], minimiza varianza.
    """
    n = len(mu)
    bounds = _bounds(n, allow_short)
    target_returns = np.linspace(mu.min(), mu.max(), n_points)
    rows = []
    
    def vol_fn(w):
        return np.sqrt(w @ cov.values @ w)
    
    for tr in target_returns:
        cons = (
            {"type": "eq", "fun": lambda w: w.sum() - 1},
            {"type": "eq", "fun": lambda w, tr=tr: w @ mu.values - tr},
        )
        x0 = np.repeat(1 / n, n)
        res = minimize(vol_fn, x0, method="SLSQP", bounds=bounds, constraints=cons)
        if res.success:
            ret, vol, sh = portfolio_perf(res.x, mu.values, cov.values)
            rows.append({"return": ret, "volatility": vol, "sharpe": sh})
    
    return pd.DataFrame(rows)
