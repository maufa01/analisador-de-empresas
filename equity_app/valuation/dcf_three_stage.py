"""
Three-stage DCF on free cash flow to the firm (FCFF).

Stage 1: explicit high-growth period (default 5y).
Stage 2: linear or logistic fade to terminal growth (default 5y).
Stage 3: Gordon-growth terminal value at year stage1+stage2.

Output is a single ``DCFResult`` carrying the projected FCFs, the
discounted PV of each year, the terminal value, the enterprise value,
and the per-share intrinsic value (after netting cash and debt).

Validation rules enforced via ``ValuationError``:
    - WACC > terminal_growth + min_spread (50bp by default)
    - Stage 1 growth clipped to [growth_cap_lower, growth_cap_upper]

The model is deliberately deterministic — Monte Carlo lives in its
own module (valuation/monte_carlo.py).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow, cagr
from core.constants import DCF_DEFAULTS
from core.exceptions import InsufficientDataError, ValuationError


FadeCurve = Literal["linear", "logistic"]


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class DCFResult:
    """Output of run_dcf — every component a downstream UI may need."""
    intrinsic_value_per_share: float
    enterprise_value: float
    equity_value: float
    pv_explicit: float
    pv_terminal: float
    terminal_value: float

    base_fcf: float
    wacc: float
    terminal_growth: float
    stage1_growth: float
    stage1_years: int
    stage2_years: int

    # Year-by-year tables (length = stage1_years + stage2_years)
    growth_path: list[float] = field(default_factory=list)
    projected_fcf: list[float] = field(default_factory=list)
    discount_factors: list[float] = field(default_factory=list)
    pv_per_year: list[float] = field(default_factory=list)


# ============================================================
# Internals
# ============================================================
def _starting_fcf(cash: pd.DataFrame) -> float:
    fcf = free_cash_flow(cash)
    if fcf is None or fcf.dropna().empty:
        raise InsufficientDataError("Cash flow statement lacks FCF / OCF / capex")
    last = float(fcf.dropna().iloc[-1])
    if last <= 0:
        raise ValuationError(
            f"Latest FCF is non-positive ({last:,.0f}); DCF requires positive cash flow"
        )
    return last


def _historical_fcf_cagr(cash: pd.DataFrame, *, max_years: int = 5) -> Optional[float]:
    """CAGR of FCF over up to ``max_years``. Returns None if not estimable."""
    fcf = free_cash_flow(cash)
    if fcf is None:
        return None
    s = fcf.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    g = cagr(s, periods=min(max_years, len(s) - 1))
    return None if not np.isfinite(g) else float(g)


def _build_growth_path(
    g1: float,
    g_terminal: float,
    stage1_years: int,
    stage2_years: int,
    curve: FadeCurve,
) -> list[float]:
    """
    Stage 1: flat g1 for stage1_years.
    Stage 2: fade from g1 to g_terminal over stage2_years.
    Returns a list of length stage1_years + stage2_years.
    """
    path = [g1] * stage1_years
    if stage2_years <= 0:
        return path

    if curve == "linear":
        for i in range(1, stage2_years + 1):
            w = i / (stage2_years + 1)            # never lands on terminal mid-fade
            path.append(g1 + (g_terminal - g1) * w)
    else:  # logistic
        for i in range(1, stage2_years + 1):
            x = (i / (stage2_years + 1)) * 12 - 6   # roughly [-6, 6]
            w = 1.0 / (1.0 + np.exp(-x))
            path.append(g1 + (g_terminal - g1) * w)
    return path


def _net_cash(balance: pd.DataFrame) -> tuple[float, float]:
    """Returns (cash, total_debt) from the most recent balance sheet row."""
    cash_s = _get(balance, "cash_eq")
    debt_s = _get(balance, "total_debt")
    cash = float(cash_s.dropna().iloc[-1]) if cash_s is not None and not cash_s.dropna().empty else 0.0
    debt = float(debt_s.dropna().iloc[-1]) if debt_s is not None and not debt_s.dropna().empty else 0.0
    return cash, debt


def _shares_outstanding(income: pd.DataFrame, balance: pd.DataFrame) -> float:
    """Pulls diluted weighted avg shares from income, falling back to balance."""
    sh = _get(income, "weighted_avg_shares")
    if sh is not None and not sh.dropna().empty:
        return float(sh.dropna().iloc[-1])
    sh = _get(balance, "common_shares_outstanding")
    if sh is not None and not sh.dropna().empty:
        return float(sh.dropna().iloc[-1])
    raise InsufficientDataError("Cannot find share count in income or balance")


# ============================================================
# Public API
# ============================================================
def run_dcf(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    wacc: float,
    stage1_growth: Optional[float] = None,
    stage1_years: Optional[int] = None,
    stage2_years: Optional[int] = None,
    terminal_growth: Optional[float] = None,
    fade_curve: Optional[FadeCurve] = None,
) -> DCFResult:
    """
    Run a three-stage FCFF DCF.

    ``stage1_growth`` defaults to historical FCF CAGR (clipped to the
    DCF caps). All year/growth params fall back to ``DCF_DEFAULTS``.
    """
    s1y = int(stage1_years if stage1_years is not None else DCF_DEFAULTS["stage1_years"])
    s2y = int(stage2_years if stage2_years is not None else DCF_DEFAULTS["stage2_years"])
    g_t = float(terminal_growth if terminal_growth is not None else DCF_DEFAULTS["terminal_growth"])
    curve: FadeCurve = (fade_curve or DCF_DEFAULTS["fade_curve"])  # type: ignore[assignment]

    spread = float(DCF_DEFAULTS["min_wacc_terminal_spread"])
    if wacc - g_t < spread:
        raise ValuationError(
            f"WACC ({wacc:.2%}) must exceed terminal growth ({g_t:.2%}) "
            f"by at least {spread:.0%}"
        )

    base_fcf = _starting_fcf(cash)

    if stage1_growth is None:
        hist = _historical_fcf_cagr(cash)
        stage1_growth = hist if hist is not None else g_t
    g1 = float(np.clip(
        stage1_growth,
        DCF_DEFAULTS["growth_cap_lower"],
        DCF_DEFAULTS["growth_cap_upper"],
    ))

    growth_path = _build_growth_path(g1, g_t, s1y, s2y, curve)

    projected: list[float] = []
    fcf_t = base_fcf
    for g in growth_path:
        fcf_t = fcf_t * (1.0 + g)
        projected.append(fcf_t)

    discount_factors = [1.0 / (1.0 + wacc) ** (t + 1) for t in range(len(projected))]
    pv_per_year = [pf * df for pf, df in zip(projected, discount_factors)]
    pv_explicit = float(sum(pv_per_year))

    final_fcf = projected[-1]
    terminal_value = final_fcf * (1.0 + g_t) / (wacc - g_t)
    pv_terminal = terminal_value * discount_factors[-1]

    enterprise_value = pv_explicit + pv_terminal
    cash_bs, debt_bs = _net_cash(balance)
    equity_value = enterprise_value + cash_bs - debt_bs
    if equity_value <= 0:
        raise ValuationError(
            f"Equity value is non-positive ({equity_value:,.0f}); "
            "net debt overwhelms enterprise value"
        )

    shares = _shares_outstanding(income, balance)
    intrinsic_per_share = equity_value / shares

    return DCFResult(
        intrinsic_value_per_share=float(intrinsic_per_share),
        enterprise_value=float(enterprise_value),
        equity_value=float(equity_value),
        pv_explicit=pv_explicit,
        pv_terminal=float(pv_terminal),
        terminal_value=float(terminal_value),
        base_fcf=float(base_fcf),
        wacc=float(wacc),
        terminal_growth=g_t,
        stage1_growth=g1,
        stage1_years=s1y,
        stage2_years=s2y,
        growth_path=[float(x) for x in growth_path],
        projected_fcf=[float(x) for x in projected],
        discount_factors=[float(x) for x in discount_factors],
        pv_per_year=[float(x) for x in pv_per_year],
    )


def sensitivity_table(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    wacc_grid: list[float],
    g_grid: list[float],
    stage1_growth: Optional[float] = None,
) -> pd.DataFrame:
    """
    Two-way sensitivity of intrinsic per-share value over WACC × terminal-g.

    Failed cells (WACC ≤ g, etc.) are returned as NaN.
    Index = WACC, columns = terminal growth.
    """
    out = pd.DataFrame(index=wacc_grid, columns=g_grid, dtype=float)
    for w in wacc_grid:
        for g in g_grid:
            try:
                r = run_dcf(
                    income=income, balance=balance, cash=cash,
                    wacc=w, terminal_growth=g, stage1_growth=stage1_growth,
                )
                out.loc[w, g] = r.intrinsic_value_per_share
            except (ValuationError, InsufficientDataError):
                out.loc[w, g] = float("nan")
    return out
