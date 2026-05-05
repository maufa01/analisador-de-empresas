"""
Black-Litterman expected returns.

Two-step pipeline:
    1. Reverse-optimisation: derive equilibrium implied returns
       ``Π = δ · Σ · w_market`` from a market-cap weight vector.
    2. Bayesian update with the user's views (P, Q, Ω) producing the
       posterior mean returns.

Usage in the Portfolio page:

    bl_returns = black_litterman_returns(
        cov=cov,
        market_weights=mc_weights,
        views=[
            View(asset="NVDA", magnitude=0.30, confidence=0.7),    # absolute
            View(asset_long="XOM", asset_short="WMT", magnitude=0.10),  # relative
        ],
    )
    res = max_sharpe(returns, expected_returns=bl_returns, ...)

Plain absolute views are the typical case; relative views work when
``asset_short`` is set.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from core.constants import PORTFOLIO_DEFAULTS


@dataclass
class View:
    """
    A single user view.

    Absolute view ⇒ ``asset_long`` only, ``asset_short=None``:
        "NVDA will return +30%" → asset_long="NVDA", magnitude=0.30
    Relative view ⇒ both assets set:
        "XOM will outperform WMT by +10%" → asset_long="XOM",
        asset_short="WMT", magnitude=0.10
    """
    asset_long: str
    magnitude: float                          # decimal, e.g. 0.30 = +30%
    asset_short: Optional[str] = None         # None ⇒ absolute view
    confidence: float = 0.5                   # 0..1; higher = more weight


# ============================================================
# Building blocks
# ============================================================
def implied_equilibrium_returns(
    *,
    cov: pd.DataFrame,
    market_weights: pd.Series,
    risk_aversion: float = 2.5,
) -> pd.Series:
    """
    Reverse-optimised equilibrium returns ``Π = δ · Σ · w``.

    Default risk-aversion δ = 2.5 ≈ Black-Litterman canonical value.
    """
    cols = list(cov.columns)
    w = market_weights.reindex(cols).fillna(0.0).values
    pi = float(risk_aversion) * (cov.values @ w)
    return pd.Series(pi, index=cols, name="implied_return")


def _build_pq_omega(
    cov: pd.DataFrame,
    views: list[View],
    *,
    tau: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert ``views`` into the (P, Q, Ω) trio expected by the BL formula.

    P (k×n): each row picks 1 (absolute) or 2 (relative) assets with
             coefficients +1 / -1.
    Q (k×1): the magnitudes.
    Ω (k×k): diagonal — confidence-derived view variance. Higher
             confidence ⇒ smaller Ω entry ⇒ stronger pull toward the view.
    """
    n = cov.shape[0]
    cols = list(cov.columns)
    P = np.zeros((len(views), n))
    Q = np.zeros(len(views))
    omega_diag = np.zeros(len(views))

    for i, v in enumerate(views):
        if v.asset_long not in cols:
            continue
        P[i, cols.index(v.asset_long)] = 1.0
        if v.asset_short and v.asset_short in cols:
            P[i, cols.index(v.asset_short)] = -1.0
        Q[i] = v.magnitude

        # Idzorek-style: σ²_view = (1 / confidence − 1) · P_i · τΣ · P_iᵀ
        c = float(np.clip(v.confidence, 0.01, 0.99))
        view_var = (1.0 / c - 1.0) * float(P[i] @ (tau * cov.values) @ P[i].T)
        omega_diag[i] = max(view_var, 1e-8)

    return P, Q, np.diag(omega_diag)


# ============================================================
# Public API
# ============================================================
def black_litterman_returns(
    *,
    cov: pd.DataFrame,
    market_weights: pd.Series,
    views: Optional[list[View]] = None,
    risk_aversion: float = 2.5,
    tau: float = 0.05,
) -> pd.Series:
    """
    Posterior mean returns under the Black-Litterman model.

    With no views the function returns the implied equilibrium returns
    (``Π``). With views it produces the BL Bayesian posterior:

        μ_BL = ((τΣ)⁻¹ + Pᵀ Ω⁻¹ P)⁻¹ ((τΣ)⁻¹ Π + Pᵀ Ω⁻¹ Q)
    """
    if cov is None or cov.empty:
        raise ValueError("cov is required")
    pi = implied_equilibrium_returns(
        cov=cov, market_weights=market_weights, risk_aversion=risk_aversion,
    )
    if not views:
        return pi

    P, Q, Omega = _build_pq_omega(cov, views, tau=tau)
    tau_sigma = tau * cov.values

    try:
        tau_sigma_inv = np.linalg.inv(tau_sigma)
        omega_inv = np.linalg.inv(Omega)
    except np.linalg.LinAlgError:
        # Pseudo-inverse fallback for ill-conditioned inputs
        tau_sigma_inv = np.linalg.pinv(tau_sigma)
        omega_inv = np.linalg.pinv(Omega)

    A = tau_sigma_inv + P.T @ omega_inv @ P
    b = tau_sigma_inv @ pi.values + P.T @ omega_inv @ Q
    posterior = np.linalg.solve(A, b)

    return pd.Series(posterior, index=cov.columns, name="bl_posterior")
