"""
Earnings Power Value — Greenblatt-style.

Capitalises normalised earning power at the company's cost of capital
in a perpetuity, WITHOUT assuming growth or a terminal value. The
result is the value of the business *as it stands today*, ignoring
upside or contraction. Robust for mature compounders (consumer
staples, healthcare, retail) where DCF / Monte Carlo tend to misprice
because growth assumptions dominate the math.

    EPV_enterprise = NOPAT / WACC
    NOPAT = avg_EBIT(N years) × (1 − tax_rate)
    Equity = EV − net_debt
    Per share = Equity / shares_outstanding

This module deliberately mirrors the calling convention of
``valuation.dcf_three_stage.run_dcf`` so the pipeline can swap it in
without changing the caller signature.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, effective_tax_rate
from core.exceptions import InsufficientDataError, ValuationError


@dataclass
class EPVResult:
    intrinsic_value_per_share: float
    enterprise_value: float
    equity_value: float
    avg_ebit: float
    normalized_nopat: float
    wacc: float
    tax_rate: float
    normalization_years: int
    net_debt: float


def _last_or_zero(series: Optional[pd.Series]) -> float:
    if series is None:
        return 0.0
    s = series.dropna()
    if s.empty:
        return 0.0
    v = float(s.iloc[-1])
    return v if np.isfinite(v) else 0.0


def _resolve_total_debt(balance: pd.DataFrame) -> float:
    """Mirrors analysis.ratios._resolve_total_debt: prefer total_debt
    when present, otherwise reconstruct from LT + ST debt."""
    debt = _get(balance, "total_debt")
    if debt is not None and not debt.dropna().empty:
        return _last_or_zero(debt)
    ltd = _get(balance, "long_term_debt")
    std = _get(balance, "short_term_debt")
    if ltd is None and std is None:
        return 0.0
    ltd_v = _last_or_zero(ltd)
    std_v = _last_or_zero(std)
    return ltd_v + std_v


def run_epv(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    wacc: float,
    shares_outstanding: float,
    tax_rate: Optional[float] = None,
    normalization_years: int = 5,
) -> EPVResult:
    """Compute Earnings Power Value per share.

    Raises:
      ValuationError      — wacc <= 0 (can't capitalise a zero-cost stream)
      InsufficientDataError — missing EBIT history, share count <= 0, or
                              avg_EBIT non-positive (steady-state EPV is
                              undefined for unprofitable businesses).
    """
    if wacc is None or not np.isfinite(wacc) or wacc <= 0:
        raise ValuationError("WACC must be positive for EPV perpetuity")
    if shares_outstanding is None or shares_outstanding <= 0:
        raise InsufficientDataError("Shares outstanding required for EPV")

    ebit = _get(income, "ebit")
    if ebit is None or ebit.dropna().empty:
        raise InsufficientDataError("EBIT not available — cannot compute EPV")

    # Use as many years as available, capped at normalization_years, min 2
    series = ebit.dropna()
    n_available = len(series)
    if n_available < 2:
        raise InsufficientDataError(
            f"Need ≥2 years of EBIT, got {n_available}"
        )
    n = min(int(normalization_years), n_available)
    used = series.tail(n)
    avg_ebit = float(used.mean())
    if avg_ebit <= 0:
        raise InsufficientDataError(
            f"Average EBIT over last {n} years is non-positive "
            f"({avg_ebit:.0f}) — EPV undefined for unprofitable steady-state"
        )

    # Tax rate: caller override > derived effective rate > 21% fallback
    if tax_rate is None:
        try:
            tax_rate = effective_tax_rate(income, periods=3)
        except Exception:
            tax_rate = 0.21
    # Defensive: clamp to a sane band even if caller passed nonsense
    tax_rate = float(np.clip(tax_rate, 0.0, 0.50))

    nopat = avg_ebit * (1.0 - tax_rate)
    enterprise_value = nopat / wacc

    cash = _get(balance, "cash_eq")
    net_debt = _resolve_total_debt(balance) - _last_or_zero(cash)
    equity_value = enterprise_value - net_debt
    per_share = equity_value / float(shares_outstanding)

    return EPVResult(
        intrinsic_value_per_share=float(per_share),
        enterprise_value=float(enterprise_value),
        equity_value=float(equity_value),
        avg_ebit=float(avg_ebit),
        normalized_nopat=float(nopat),
        wacc=float(wacc),
        tax_rate=float(tax_rate),
        normalization_years=int(n),
        net_debt=float(net_debt),
    )
