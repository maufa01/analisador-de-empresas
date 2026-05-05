"""
Residual Income (Edwards-Bell-Ohlson) valuation.

    Equity Value = Book Value + Σ PV(Residual Income)
    Residual Income_t = NI_t − r_e · BV_{t-1}

The model is preferred over FCFF DCF for financials (banks, insurers)
where the line between operating and financing cash is blurry and FCF
can be misleading.

Two stages here:
- Stage 1: explicit RI projection for ``stage1_years`` based on a
  forward ROE growth assumption.
- Stage 2: terminal RI in perpetuity, discounted by (re − g_t).

Like DDM, the discount rate is the **cost of equity**, not WACC.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, cagr
from core.constants import DCF_DEFAULTS
from core.exceptions import InsufficientDataError, ValuationError


# ============================================================
# Result
# ============================================================
@dataclass
class RIResult:
    intrinsic_value_per_share: float
    book_value_per_share: float
    pv_explicit_ri: float
    pv_terminal_ri: float
    cost_of_equity: float
    base_roe: float
    base_eps: float
    stage1_growth: float
    terminal_growth: float
    stage1_years: int
    projected_ri: list[float] = field(default_factory=list)


# ============================================================
# Internals
# ============================================================
def _shares_outstanding(income: pd.DataFrame, balance: pd.DataFrame) -> float:
    sh = _get(income, "weighted_avg_shares")
    if sh is not None and not sh.dropna().empty:
        return float(sh.dropna().iloc[-1])
    sh = _get(balance, "common_shares_outstanding")
    if sh is not None and not sh.dropna().empty:
        return float(sh.dropna().iloc[-1])
    raise InsufficientDataError("Cannot find share count")


def _historical_roe(income: pd.DataFrame, balance: pd.DataFrame,
                    *, max_years: int = 5) -> tuple[float, Optional[float]]:
    """Returns (mean ROE, mean ROE growth) over up to ``max_years``."""
    ni = _get(income, "net_income")
    eq = _get(balance, "total_equity")
    if ni is None or eq is None:
        raise InsufficientDataError("Need net income and total equity")
    df = pd.concat([ni, eq], axis=1).dropna().tail(max_years)
    df.columns = ["ni", "eq"]
    df = df[df["eq"] > 0]
    if df.empty:
        raise InsufficientDataError("All equity values are non-positive")
    roe_series = df["ni"] / df["eq"]
    mean_roe = float(roe_series.mean())
    g = None
    if len(roe_series) >= 2 and roe_series.iloc[0] > 0:
        c = cagr(roe_series)
        g = c if np.isfinite(c) else None
    return mean_roe, g


# ============================================================
# Public API
# ============================================================
def run_residual_income(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cost_of_equity: float,
    stage1_years: int = 5,
    stage1_growth: Optional[float] = None,
    terminal_growth: Optional[float] = None,
) -> RIResult:
    """
    Two-stage Residual Income.

    ``stage1_growth`` is applied to **net income** (not EPS) — book value
    grows by retained earnings each year (we assume zero net buybacks/
    issuance in projections).
    """
    g_t = float(terminal_growth if terminal_growth is not None
                else DCF_DEFAULTS["terminal_growth"])
    spread = float(DCF_DEFAULTS["min_wacc_terminal_spread"])
    if cost_of_equity - g_t < spread:
        raise ValuationError(
            f"Cost of equity ({cost_of_equity:.2%}) must exceed terminal growth "
            f"({g_t:.2%}) by at least {spread:.0%}"
        )

    ni_s = _get(income, "net_income")
    eq_s = _get(balance, "total_equity")
    if ni_s is None or eq_s is None:
        raise InsufficientDataError("Need net income and total equity")

    last_ni = float(ni_s.dropna().iloc[-1])
    last_bv = float(eq_s.dropna().iloc[-1])
    if last_bv <= 0:
        raise ValuationError(f"Book value is non-positive ({last_bv:,.0f})")

    base_roe = last_ni / last_bv
    shares = _shares_outstanding(income, balance)
    bvps = last_bv / shares
    eps = last_ni / shares

    # Default growth = NI CAGR, clipped to DCF caps.
    if stage1_growth is None:
        ni_clean = ni_s.dropna().tail(5)
        if len(ni_clean) >= 2 and ni_clean.iloc[0] > 0:
            cg = cagr(ni_clean)
            stage1_growth = cg if np.isfinite(cg) else g_t
        else:
            stage1_growth = g_t
    g1 = float(np.clip(
        stage1_growth,
        DCF_DEFAULTS["growth_cap_lower"],
        DCF_DEFAULTS["growth_cap_upper"],
    ))

    bv_t = last_bv
    ni_t = last_ni
    pv_explicit = 0.0
    projected_ri: list[float] = []

    for t in range(1, stage1_years + 1):
        ni_t = ni_t * (1.0 + g1)
        ri = ni_t - cost_of_equity * bv_t
        projected_ri.append(ri)
        pv_explicit += ri / (1.0 + cost_of_equity) ** t
        bv_t = bv_t + ni_t                           # zero-payout assumption

    # Terminal RI (perpetuity)
    ri_term = projected_ri[-1] * (1.0 + g_t)
    terminal_value = ri_term / (cost_of_equity - g_t)
    pv_terminal = terminal_value / (1.0 + cost_of_equity) ** stage1_years

    equity_value = last_bv + pv_explicit + pv_terminal
    if equity_value <= 0:
        raise ValuationError("Computed equity value is non-positive")

    return RIResult(
        intrinsic_value_per_share=float(equity_value / shares),
        book_value_per_share=float(bvps),
        pv_explicit_ri=float(pv_explicit / shares),
        pv_terminal_ri=float(pv_terminal / shares),
        cost_of_equity=float(cost_of_equity),
        base_roe=float(base_roe),
        base_eps=float(eps),
        stage1_growth=g1,
        terminal_growth=g_t,
        stage1_years=int(stage1_years),
        projected_ri=[float(x / shares) for x in projected_ri],
    )
