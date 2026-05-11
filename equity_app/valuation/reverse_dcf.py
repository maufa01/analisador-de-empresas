"""
Reverse DCF — solve for the stage-1 growth rate that justifies a target
price under the current WACC / terminal-growth assumptions.

Uses Brent's method on the deterministic ``run_dcf`` function. The
function is monotone-ish in stage-1 growth (higher growth → higher
intrinsic) so a bracketed root-finder converges reliably.

Returns the implied growth plus comparison anchors (historical CAGR,
optional industry average) and a plain-English interpretation so the
UI can render the result without re-doing the analysis.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, cagr
from core.constants import DCF_DEFAULTS
from core.exceptions import InsufficientDataError, ValuationError
from valuation.dcf_three_stage import run_dcf


@dataclass
class ReverseDCFResult:
    implied_growth: Optional[float]                  # decimal, e.g. 0.184 = 18.4%
    target_price: float
    wacc: float
    terminal_growth: float
    historical_growth: Optional[float]               # 5y revenue CAGR
    industry_growth: Optional[float] = None
    interpretation: str = ""
    error: Optional[str] = None


# ============================================================
# Helpers
# ============================================================
def _historical_revenue_cagr(income: pd.DataFrame, *, years: int = 5) -> Optional[float]:
    rev = _get(income, "revenue")
    if rev is None or len(rev.dropna()) < 2:
        return None
    s = rev.dropna()
    if s.iloc[0] <= 0:
        return None
    g = cagr(s, periods=min(years, len(s) - 1))
    return None if not np.isfinite(g) else float(g)


def _interpret(
    implied: float,
    historical: Optional[float],
    industry: Optional[float],
) -> str:
    if implied < 0:
        return ("Market is pricing in revenue **decline** — the current "
                "price implies the business contracts. Consider what the "
                "market sees that the historical record doesn't.")
    if historical is None:
        return (f"Market expects ~{implied:.1%} stage-1 growth. "
                "Insufficient history to compare with realised growth.")
    # Evaluate by BOTH absolute gap (pp) and ratio. Ratio alone is
    # misleading for low-growth bases: 17.3% vs 11.8% is ratio 1.47
    # (looks "fair") but the +5.5pp absolute gap is material.
    gap_pp = (implied - historical) * 100.0
    ratio = implied / historical if historical > 0 else float("inf")
    if gap_pp >= 3.0 and ratio >= 1.3:
        return (f"Market expects **{implied:.1%}** stage-1 growth — "
                f"above the historical {historical:.1%} CAGR "
                f"(+{gap_pp:.1f}pp). Pricing implies **acceleration**; "
                "needs a credible thesis for the gap.")
    if gap_pp <= -3.0 and ratio <= 0.7:
        return (f"Market expects only **{implied:.1%}** vs the "
                f"historical {historical:.1%} CAGR ({gap_pp:.1f}pp). "
                "Pricing implies **deceleration** — look for catalysts.")
    base = (f"Market expectations broadly align with realised growth "
            f"({implied:.1%} implied vs {historical:.1%} historical, "
            f"{gap_pp:+.1f}pp). Pricing looks fair on the growth dimension.")
    if industry is not None and abs(implied - industry) > 0.05:
        base += (f" Industry average growth is {industry:.1%} — "
                 f"{'above' if implied > industry else 'below'} sector trend.")
    return base


# ============================================================
# Public API
# ============================================================
def run_reverse_dcf(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    target_price: float,
    wacc: float,
    terminal_growth: Optional[float] = None,
    stage1_years: Optional[int] = None,
    stage2_years: Optional[int] = None,
    industry_growth: Optional[float] = None,
    search_lo: float = -0.10,
    search_hi: float = 0.50,
) -> ReverseDCFResult:
    """
    Solve for the stage-1 growth that makes ``run_dcf`` produce a per-share
    intrinsic equal to ``target_price``.

    Returns a ``ReverseDCFResult``; ``implied_growth=None`` when no
    solution exists in the [search_lo, search_hi] bracket.
    """
    g_t = float(terminal_growth if terminal_growth is not None
                else DCF_DEFAULTS["terminal_growth"])

    historical = _historical_revenue_cagr(income)

    def _diff(g: float) -> float:
        try:
            res = run_dcf(
                income=income, balance=balance, cash=cash,
                wacc=wacc, stage1_growth=g,
                stage1_years=stage1_years, stage2_years=stage2_years,
                terminal_growth=g_t,
            )
            return res.intrinsic_value_per_share - target_price
        except (ValuationError, InsufficientDataError):
            return float("inf")

    f_lo, f_hi = _diff(search_lo), _diff(search_hi)
    if not (np.isfinite(f_lo) and np.isfinite(f_hi)) or f_lo * f_hi > 0:
        return ReverseDCFResult(
            implied_growth=None,
            target_price=float(target_price),
            wacc=float(wacc),
            terminal_growth=g_t,
            historical_growth=historical,
            industry_growth=industry_growth,
            error=(
                f"No solution in growth range [{search_lo:.0%}, {search_hi:.0%}]. "
                "Target price falls outside the achievable intrinsic band; "
                "try widening the range or relaxing the WACC."
            ),
        )

    try:
        from scipy.optimize import brentq                   # type: ignore
        implied = float(brentq(_diff, search_lo, search_hi, xtol=1e-4, maxiter=80))
    except (ValueError, ImportError) as exc:
        return ReverseDCFResult(
            implied_growth=None,
            target_price=float(target_price),
            wacc=float(wacc),
            terminal_growth=g_t,
            historical_growth=historical,
            industry_growth=industry_growth,
            error=str(exc),
        )

    return ReverseDCFResult(
        implied_growth=implied,
        target_price=float(target_price),
        wacc=float(wacc),
        terminal_growth=g_t,
        historical_growth=historical,
        industry_growth=industry_growth,
        interpretation=_interpret(implied, historical, industry_growth),
    )
