"""
Portfolio constraints: position bounds and sector / group caps.

Returns SLSQP-ready ``bounds`` and ``constraints`` lists. The ``budget``
constraint (∑w = 1) is always included; long-only is the default.

Typical usage:

    bounds, cons = build_constraints(
        tickers=["AAPL", "MSFT", "JPM"],
        sector_map={"AAPL": "Tech", "MSFT": "Tech", "JPM": "Financials"},
        max_position=0.30,
        sector_caps={"Tech": 0.40},
    )
    res = scipy.optimize.minimize(..., bounds=bounds, constraints=cons)
"""
from __future__ import annotations
from typing import Iterable, Optional

import numpy as np

from core.constants import PORTFOLIO_DEFAULTS


# ============================================================
# Public API
# ============================================================
def build_constraints(
    *,
    tickers: list[str],
    sector_map: Optional[dict[str, str]] = None,
    max_position: float = PORTFOLIO_DEFAULTS["max_position_size"],
    min_position: float = PORTFOLIO_DEFAULTS["min_position_size"],
    sector_caps: Optional[dict[str, float]] = None,
    allow_short: bool = False,
    target_return: Optional[float] = None,
    expected_returns: Optional[np.ndarray] = None,
) -> tuple[list[tuple[float, float]], list[dict]]:
    """
    Build (bounds, constraints) for ``scipy.optimize.minimize``.

    - ``min_position`` is enforced as a lower bound on the box constraints.
      For long-only, this means every name carries at least this weight.
      Pass ``min_position=0`` to allow zero positions.
    - ``sector_caps`` maps sector name → max fraction of portfolio.
      Sectors not listed are uncapped.
    - ``target_return``, when given, adds an equality constraint
      ``w · expected_returns == target_return``. Required for the
      efficient-frontier sweep.
    """
    n = len(tickers)
    if allow_short:
        bounds = [(-max_position, max_position)] * n
    else:
        bounds = [(min_position, max_position)] * n

    cons: list[dict] = [
        {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    ]

    if sector_caps and sector_map:
        for sector, cap in sector_caps.items():
            idx = [i for i, t in enumerate(tickers) if sector_map.get(t) == sector]
            if not idx:
                continue
            mask = np.zeros(n, dtype=float)
            mask[idx] = 1.0
            cons.append({
                "type": "ineq",
                "fun": lambda w, mask=mask, cap=cap: float(cap - mask @ w),
            })

    if target_return is not None:
        if expected_returns is None:
            raise ValueError(
                "target_return requires expected_returns to be provided"
            )
        mu = np.asarray(expected_returns, dtype=float)
        if mu.shape[0] != n:
            raise ValueError(
                f"expected_returns length {mu.shape[0]} != n_assets {n}"
            )
        cons.append({
            "type": "eq",
            "fun": lambda w, mu=mu, t=float(target_return): float(w @ mu - t),
        })

    return bounds, cons


# ============================================================
# Validation helpers
# ============================================================
def check_weights(
    weights: np.ndarray,
    *,
    tol: float = 1e-4,
    bounds: Optional[Iterable[tuple[float, float]]] = None,
) -> dict:
    """
    Diagnostic: returns flags for ∑w ≈ 1 and per-bound respect.

    Used by tests; the optimizer itself trusts SLSQP's constraint engine.
    """
    w = np.asarray(weights, dtype=float)
    out = {
        "sums_to_one": bool(abs(w.sum() - 1.0) < tol),
        "weight_sum": float(w.sum()),
        "n_zero": int((np.abs(w) < tol).sum()),
        "max_weight": float(w.max()),
        "min_weight": float(w.min()),
    }
    if bounds is not None:
        violations = []
        for i, (lo, hi) in enumerate(bounds):
            if w[i] < lo - tol or w[i] > hi + tol:
                violations.append(i)
        out["bound_violations"] = violations
    return out
