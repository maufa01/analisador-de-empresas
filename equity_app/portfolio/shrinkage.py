"""
Covariance shrinkage and exponentially-weighted covariance estimators.

The sample covariance matrix is noisy when N (assets) ~ T (observations) —
its largest eigenvalues are biased upward and the smallest downward, which
is exactly the worst case for mean-variance optimization (which loads on
the lowest-eigenvalue directions).

Two shrinkage estimators are provided:

- ``ledoit_wolf`` shrinks the sample covariance toward a structured
  target (a scaled identity matrix), with the shrinkage intensity chosen
  analytically to minimise expected MSE. We delegate to
  ``sklearn.covariance.LedoitWolf`` when available, fallback to a hand
  implementation of the analytical formula.
- ``ewma_cov`` weights recent observations more heavily — useful in
  regimes where volatility has changed.

Both return DataFrames preserving the input column order so weights can
be aligned downstream.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ShrinkageResult:
    covariance: pd.DataFrame
    shrinkage: float          # in [0, 1] — fraction of weight on the target
    method: str               # "sklearn" | "analytical" | "ewma"


# ============================================================
# Analytical Ledoit-Wolf (fallback when sklearn is missing)
# ============================================================
def _analytical_ledoit_wolf(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Ledoit & Wolf (2004) "A well-conditioned estimator for large-dimensional
    covariance matrices". Target = (trace(S)/N) · I.

    Returns (shrunk_covariance, shrinkage_intensity).
    """
    t, n = returns.shape
    x = returns - returns.mean(axis=0, keepdims=True)
    s = (x.T @ x) / t                             # sample covariance (MLE)

    mu = float(np.trace(s) / n)
    f = mu * np.eye(n)                            # target

    # Frobenius-norm distance from sample to target
    d2 = float(np.sum((s - f) ** 2))

    # Asymptotic variance of sample-cov entries
    pi_mat = np.zeros_like(s)
    for k in range(t):
        xk = x[k:k + 1]
        pi_mat += (xk.T @ xk - s) ** 2
    pi = float(np.sum(pi_mat) / t)

    # No off-target term to estimate when target is scaled identity
    kappa = pi / d2 if d2 > 0 else 0.0
    delta = float(np.clip(kappa / t, 0.0, 1.0))

    shrunk = delta * f + (1 - delta) * s
    return shrunk, delta


# ============================================================
# Public — Ledoit-Wolf
# ============================================================
def ledoit_wolf(returns: pd.DataFrame, *, annualize: int = 252) -> ShrinkageResult:
    """
    Ledoit-Wolf shrinkage covariance.

    ``returns`` must be a periodic returns DataFrame (rows = periods,
    columns = assets). The output is annualized by ``annualize`` (252 for
    daily, 12 for monthly, etc.) — pass 1 to keep it in native units.
    """
    if returns is None or returns.empty:
        raise ValueError("returns DataFrame is empty")
    if returns.shape[0] < 2:
        raise ValueError("Need at least 2 return observations")

    cleaned = returns.dropna(how="any")
    cols = cleaned.columns

    try:
        from sklearn.covariance import LedoitWolf  # type: ignore
        lw = LedoitWolf().fit(cleaned.values)
        cov = pd.DataFrame(lw.covariance_, index=cols, columns=cols) * annualize
        return ShrinkageResult(
            covariance=cov,
            shrinkage=float(lw.shrinkage_),
            method="sklearn",
        )
    except ImportError:
        pass

    cov_arr, delta = _analytical_ledoit_wolf(cleaned.values)
    cov = pd.DataFrame(cov_arr, index=cols, columns=cols) * annualize
    return ShrinkageResult(covariance=cov, shrinkage=delta, method="analytical")


# ============================================================
# Public — EWMA
# ============================================================
def ewma_cov(
    returns: pd.DataFrame,
    *,
    halflife: int = 60,
    annualize: int = 252,
) -> ShrinkageResult:
    """
    Exponentially-weighted covariance using pandas' ``ewm``.

    ``halflife`` is in periods. Defaults to 60 (≈3 trading months).
    """
    if returns is None or returns.empty:
        raise ValueError("returns DataFrame is empty")

    cleaned = returns.dropna(how="any")
    n_obs, n = cleaned.shape
    if n_obs < 2:
        raise ValueError("Need at least 2 return observations")

    cov_long = cleaned.ewm(halflife=halflife).cov(pairwise=True)
    last_idx = cov_long.index.get_level_values(0).unique()[-1]
    cov = cov_long.loc[last_idx] * annualize

    return ShrinkageResult(
        covariance=cov.reindex(index=cleaned.columns, columns=cleaned.columns),
        shrinkage=0.0,
        method="ewma",
    )
