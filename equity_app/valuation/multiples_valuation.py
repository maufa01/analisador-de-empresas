"""
Sector-multiple based valuation.

Triangulates three implied per-share prices using sector median
multiples (Damodaran-style), then returns their median as the point
estimate. Distinct from ``valuation.comparables`` (which uses live
peer fundamentals) — this module is a static benchmark anchor that
works even when peer hydration fails.

Multiples used:
    P/E          → implied = EPS × sector_P/E
    EV/EBITDA    → implied EV − net_debt → per share
    P/FCF        → implied = (FCF / shares) × (1 / sector_FCF_yield)

Sector multiples come from ``data.industry_benchmarks.INDUSTRY_BENCHMARKS``
(``pe_ratio``, ``ev_to_ebitda``, ``fcf_yield``). Sectors missing one
of these (e.g. Financial Services has no ev_to_ebitda) simply emit
None for that multiple — the median is computed over what survives.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow
from core.exceptions import InsufficientDataError
from data.industry_benchmarks import get_benchmark, normalise_sector


# Fallback when the resolved sector has no benchmarks at all (or the
# string didn't normalise to a known canonical sector).
_DEFAULT_MULTIPLES = {"pe_ratio": 18.0, "ev_to_ebitda": 12.0, "fcf_yield": 0.05}


@dataclass
class MultiplesResult:
    implied_per_share_median: float
    implied_per_share_pe: Optional[float]
    implied_per_share_evebitda: Optional[float]
    implied_per_share_pfcf: Optional[float]
    sector_median_pe: Optional[float]
    sector_median_evebitda: Optional[float]
    sector_median_pfcf: Optional[float]          # = 1 / fcf_yield
    sector_used: str


def _last_finite(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    s = series.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if np.isfinite(v) else None


def _resolve_total_debt(balance: pd.DataFrame) -> float:
    debt = _get(balance, "total_debt")
    last = _last_finite(debt) if debt is not None else None
    if last is not None:
        return last
    ltd = _last_finite(_get(balance, "long_term_debt")) or 0.0
    std = _last_finite(_get(balance, "short_term_debt")) or 0.0
    return ltd + std


def _resolve_ebitda(income: pd.DataFrame, cash: pd.DataFrame) -> Optional[float]:
    """Latest fiscal-year EBITDA. Reconstructs EBIT + D&A when EBITDA
    isn't reported directly."""
    direct = _last_finite(_get(income, "ebitda"))
    if direct is not None:
        return direct
    ebit_last = _last_finite(_get(income, "ebit"))
    da_last = _last_finite(_get(cash, "depreciation_cf"))
    if da_last is None:
        da_last = _last_finite(_get(income, "depreciation_inc"))
    if ebit_last is None or da_last is None:
        return None
    return ebit_last + da_last


def run_multiples_valuation(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    sector: Optional[str],
    shares_outstanding: float,
) -> MultiplesResult:
    if shares_outstanding is None or shares_outstanding <= 0:
        raise InsufficientDataError("Shares outstanding required for multiples")

    canonical = normalise_sector(sector) or "_default"

    pe_mult = get_benchmark(canonical, "pe_ratio") or _DEFAULT_MULTIPLES["pe_ratio"]
    ev_ebitda_mult = get_benchmark(canonical, "ev_to_ebitda")
    fcf_yield = get_benchmark(canonical, "fcf_yield")
    p_fcf_mult = (1.0 / fcf_yield) if (fcf_yield and fcf_yield > 0) else None

    # ---- Per-share implied prices ----
    net_income = _last_finite(_get(income, "net_income"))
    eps = (net_income / shares_outstanding) if net_income is not None else None
    implied_pe = (eps * pe_mult) if (eps is not None and eps > 0) else None

    ebitda = _resolve_ebitda(income, cash)
    if ebitda is not None and ebitda > 0 and ev_ebitda_mult is not None:
        net_debt = _resolve_total_debt(balance) - (_last_finite(_get(balance, "cash_eq")) or 0.0)
        implied_ev = ebitda * ev_ebitda_mult
        implied_equity = implied_ev - net_debt
        implied_evebitda = implied_equity / shares_outstanding
    else:
        implied_evebitda = None

    fcf_series = free_cash_flow(cash)
    fcf_last = _last_finite(fcf_series)
    if fcf_last is not None and fcf_last > 0 and p_fcf_mult is not None:
        implied_pfcf = (fcf_last * p_fcf_mult) / shares_outstanding
    else:
        implied_pfcf = None

    # Median across surviving multiples
    survivors = [v for v in (implied_pe, implied_evebitda, implied_pfcf)
                 if v is not None and np.isfinite(v) and v > 0]
    if not survivors:
        raise InsufficientDataError(
            "All three multiples non-applicable (no positive EPS, EBITDA, or FCF)"
        )
    median_v = float(np.median(survivors))

    return MultiplesResult(
        implied_per_share_median=median_v,
        implied_per_share_pe=implied_pe,
        implied_per_share_evebitda=implied_evebitda,
        implied_per_share_pfcf=implied_pfcf,
        sector_median_pe=float(pe_mult),
        sector_median_evebitda=(float(ev_ebitda_mult)
                                 if ev_ebitda_mult is not None else None),
        sector_median_pfcf=(float(p_fcf_mult)
                             if p_fcf_mult is not None else None),
        sector_used=canonical if canonical != "_default" else "default",
    )
