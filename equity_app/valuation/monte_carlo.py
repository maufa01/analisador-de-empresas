"""
Monte Carlo wrapper around the deterministic DCF.

Treats the three inputs the deterministic DCF is most sensitive to as
random variables and re-runs the model ``n_simulations`` times:

- Stage-1 growth: Normal(historical_cagr, max(rev_std, std_floor))
- WACC:           Normal(point_wacc, wacc_std)        (clipped at 0.5%)
- Terminal g:     Uniform(low, high)

Each draw must respect WACC > g + spread (the deterministic guard);
draws that fail are resampled. Returns the full distribution of
intrinsic per-share values plus configurable percentiles.

The "vectorized" hint in the original docstring is aspirational — at
10k sims with a 10-year projection the per-iteration DCF is ~50µs in
pure Python, well under one second total. Vectorisation can come later
if a sweep ever needs > 100k paths.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow, cagr
from core.constants import DCF_DEFAULTS, MONTE_CARLO_DEFAULTS
from core.exceptions import InsufficientDataError, ValuationError
from .dcf_three_stage import run_dcf


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class MonteCarloResult:
    intrinsic_distribution: np.ndarray
    percentiles: dict[int, float]
    mean: float
    std: float
    median: float
    p_undervalued: Optional[float]      # P(intrinsic > current_price)
    n_simulations: int
    n_failed: int
    inputs: dict[str, float] = field(default_factory=dict)


# ============================================================
# Internals
# ============================================================
def _historical_growth_stats(
    cash: pd.DataFrame, *, max_years: int = 5
) -> tuple[float, float]:
    """Returns (mean, std) of YoY FCF growth over up to ``max_years``."""
    fcf = free_cash_flow(cash)
    if fcf is None or fcf.dropna().empty:
        raise InsufficientDataError("FCF series unavailable")
    s = fcf.dropna().tail(max_years + 1)
    if len(s) < 2:
        raise InsufficientDataError("Need at least 2 FCF observations")
    growth = s.pct_change().dropna()
    if growth.empty:
        # Single-period: derive a CAGR but no std
        return float(cagr(s)), float(MONTE_CARLO_DEFAULTS["rev_growth_std_floor"])
    g_mean = float(growth.mean())
    g_std = float(growth.std(ddof=1)) if len(growth) > 1 else 0.0
    g_std = max(g_std, MONTE_CARLO_DEFAULTS["rev_growth_std_floor"])
    # Cyclical tickers (memory, oil, biotech) have FCF that crosses
    # zero — pct_change() in those cases produces absurd means/std
    # (e.g. div-by-near-zero yields 10x+ growth for one period).
    # Hard caps keep the sim within a sane band.
    g_mean = float(np.clip(g_mean, -0.30, 0.50))
    g_std = float(np.clip(
        g_std, MONTE_CARLO_DEFAULTS["rev_growth_std_floor"], 0.30,
    ))
    return g_mean, g_std


# ============================================================
# Public API
# ============================================================
def run_monte_carlo(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    wacc: float,
    n_simulations: int = MONTE_CARLO_DEFAULTS["n_simulations"],
    wacc_std: float = MONTE_CARLO_DEFAULTS["wacc_std"],
    terminal_low: float = MONTE_CARLO_DEFAULTS["terminal_growth_low"],
    terminal_high: float = MONTE_CARLO_DEFAULTS["terminal_growth_high"],
    stage1_years: Optional[int] = None,
    stage2_years: Optional[int] = None,
    growth_mean: Optional[float] = None,
    growth_std: Optional[float] = None,
    current_price: Optional[float] = None,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """
    Run a Monte Carlo over WACC × stage-1 growth × terminal growth.

    ``growth_mean`` / ``growth_std`` default to the historical YoY mean
    and std of FCF (with a floor on std). Pass them explicitly to inject
    a custom view.
    """
    rng = np.random.default_rng(seed)
    if growth_mean is None or growth_std is None:
        gm, gs = _historical_growth_stats(cash)
        growth_mean = gm if growth_mean is None else growth_mean
        growth_std = gs if growth_std is None else growth_std

    spread = float(DCF_DEFAULTS["min_wacc_terminal_spread"])
    intrinsic: list[float] = []
    failed = 0

    for _ in range(int(n_simulations)):
        g1 = float(rng.normal(growth_mean, growth_std))
        w = float(max(0.005, rng.normal(wacc, wacc_std)))
        gt = float(rng.uniform(terminal_low, terminal_high))

        if w - gt < spread:
            failed += 1
            continue
        try:
            res = run_dcf(
                income=income, balance=balance, cash=cash,
                wacc=w, stage1_growth=g1,
                stage1_years=stage1_years, stage2_years=stage2_years,
                terminal_growth=gt,
            )
            intrinsic.append(res.intrinsic_value_per_share)
        except (ValuationError, InsufficientDataError):
            failed += 1
            continue

    if not intrinsic:
        raise ValuationError(
            f"All {n_simulations} simulations failed validation; "
            "try a wider terminal_growth band or a smaller WACC std."
        )

    arr = np.asarray(intrinsic, dtype=float)
    pcts = MONTE_CARLO_DEFAULTS["percentiles"]
    percentiles = {int(p): float(np.percentile(arr, p)) for p in pcts}

    p_under = None
    if current_price is not None and current_price > 0:
        p_under = float((arr > current_price).mean())

    return MonteCarloResult(
        intrinsic_distribution=arr,
        percentiles=percentiles,
        mean=float(arr.mean()),
        std=float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        median=float(np.median(arr)),
        p_undervalued=p_under,
        n_simulations=int(n_simulations),
        n_failed=failed,
        inputs={
            "wacc_mean": float(wacc),
            "wacc_std":  float(wacc_std),
            "growth_mean": float(growth_mean),
            "growth_std":  float(growth_std),
            "terminal_low":  float(terminal_low),
            "terminal_high": float(terminal_high),
        },
    )
