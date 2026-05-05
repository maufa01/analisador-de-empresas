"""
Capital allocation analysis — how much cash the company has returned
to shareholders (buybacks + dividends), how much it has reinvested
(CapEx + M&A), and the incremental ROIC on the capital deployed.

The cash-flow statement uses sign conventions where outflows are
negative (e.g. ``capitalExpenditure = -10.5B``); we surface absolute
totals for the dashboard and keep raw series for the stacked bar.

Returns a single ``CapitalAllocationResult`` dataclass with everything
the UI needs to render.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import math
import numpy as np
import pandas as pd

from analysis.ratios import _get


@dataclass
class CapitalAllocationFlag:
    icon: str          # "✓" | "⚠" | "✗"
    text: str


@dataclass
class CapitalAllocationResult:
    years: int
    annual_cf: pd.DataFrame                          # raw per-year numbers
    totals: dict[str, float]                         # absolute totals
    as_pct_market_cap: dict[str, Optional[float]]    # totals / mkt cap
    shareholder_yield_annualised: Optional[float]
    incremental_roic: Optional[float]
    cash_conversion: Optional[float]                 # FCF / Net Income
    score: int
    flags: list[CapitalAllocationFlag] = field(default_factory=list)


# ============================================================
# Internals
# ============================================================
def _abs_sum(s: Optional[pd.Series]) -> float:
    if s is None:
        return 0.0
    return float(s.dropna().abs().sum())


def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _annualise_yield(total: float, years: int, market_cap: Optional[float]) -> Optional[float]:
    """Convert a multi-year total into an annualised yield as % of market cap."""
    if market_cap is None or market_cap <= 0 or years <= 0:
        return None
    return (total / market_cap) / years


def _incremental_roic(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    *,
    tax_rate: float = 0.21,
) -> Optional[float]:
    """
    ΔNOPAT / ΔInvestedCapital between the first and last year of the
    available history. NOPAT ≈ EBIT × (1 − tax). Invested Capital ≈
    Total Assets − Current Liabilities.
    """
    ebit = _get(income, "operating_income")
    assets = _get(balance, "total_assets")
    cur_liab = _get(balance, "current_liabilities")
    if ebit is None or assets is None or cur_liab is None:
        return None
    ebit_clean = ebit.dropna()
    assets_clean = assets.dropna()
    liab_clean = cur_liab.dropna()
    if (len(ebit_clean) < 2 or len(assets_clean) < 2 or len(liab_clean) < 2):
        return None

    nopat_first = float(ebit_clean.iloc[0])  * (1.0 - tax_rate)
    nopat_last  = float(ebit_clean.iloc[-1]) * (1.0 - tax_rate)
    inv_first = float(assets_clean.iloc[0])  - float(liab_clean.iloc[0])
    inv_last  = float(assets_clean.iloc[-1]) - float(liab_clean.iloc[-1])

    delta_inv = inv_last - inv_first
    if delta_inv == 0 or not math.isfinite(delta_inv):
        return None
    delta_nopat = nopat_last - nopat_first
    return delta_nopat / delta_inv


def _score_and_flag(
    *,
    incremental_roic: Optional[float],
    buybacks_pct: Optional[float],
    cash_conv: Optional[float],
    acquisitions_pct: Optional[float],
) -> tuple[int, list[CapitalAllocationFlag]]:
    """Heuristic 0-100 score + human-readable flags. Anchor: 50."""
    score = 50
    flags: list[CapitalAllocationFlag] = []

    if incremental_roic is not None:
        if incremental_roic >= 0.20:
            score += 20
            flags.append(CapitalAllocationFlag(
                "✓", f"Excellent incremental ROIC {incremental_roic:.1%} — well above WACC."
            ))
        elif incremental_roic >= 0.10:
            score += 8
            flags.append(CapitalAllocationFlag(
                "✓", f"Solid incremental ROIC {incremental_roic:.1%}."
            ))
        elif incremental_roic < 0.05:
            score -= 20
            flags.append(CapitalAllocationFlag(
                "✗",
                f"Poor incremental ROIC {incremental_roic:.1%} — capital being deployed at sub-WACC returns.",
            ))

    if buybacks_pct is not None and buybacks_pct >= 0.30:
        score += 10
        flags.append(CapitalAllocationFlag(
            "✓", f"Aggressive buyback program — {buybacks_pct:.0%} of market cap returned."
        ))
    elif buybacks_pct is not None and buybacks_pct < 0.05:
        flags.append(CapitalAllocationFlag(
            "⚠", "Minimal buybacks — capital may be parked or misallocated."
        ))

    if cash_conv is not None:
        if cash_conv > 1.05:
            score += 10
            flags.append(CapitalAllocationFlag(
                "✓",
                f"Cash conversion {cash_conv:.0%} — FCF runs ahead of reported earnings.",
            ))
        elif cash_conv < 0.70:
            score -= 10
            flags.append(CapitalAllocationFlag(
                "⚠",
                f"Weak cash conversion {cash_conv:.0%} — earnings outpace actual cash generation.",
            ))

    if acquisitions_pct is not None and acquisitions_pct < 0.02:
        flags.append(CapitalAllocationFlag(
            "⚠",
            "Low M&A activity — possibly missing inorganic growth opportunities.",
        ))

    return int(np.clip(score, 0, 100)), flags


# ============================================================
# Public API
# ============================================================
def analyze_capital_allocation(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    market_cap: Optional[float] = None,
) -> CapitalAllocationResult:
    """Compute the capital-allocation summary across whatever years of
    cash-flow history the caller provides. Tolerates missing fields."""
    years = max(int(len(cash.dropna(how="all"))), 1)

    buybacks   = _get(cash, "buybacks")
    dividends  = _get(cash, "dividends_paid")
    capex      = _get(cash, "capex")
    ocf        = _get(cash, "ocf")
    da         = _get(cash, "depreciation_cf")
    sbc        = _get(cash, "sbc")
    ni         = _get(income, "net_income")

    # `acquisitionsNet` sometimes ships as a column on FMP — try a
    # raw-key resolution first then fall through.
    acquisitions: Optional[pd.Series] = None
    if "acquisitionsNet" in cash.columns:
        try:
            acquisitions = cash["acquisitionsNet"].astype(float)
        except Exception:
            acquisitions = None

    total_buybacks    = _abs_sum(buybacks)
    total_dividends   = _abs_sum(dividends)
    total_capex       = _abs_sum(capex)
    total_acquisitions = _abs_sum(acquisitions)
    total_returned    = total_buybacks + total_dividends

    # Cash conversion (FCF / Net Income) over the full window
    fcf_total = (
        float(ocf.dropna().sum() + capex.dropna().sum())
        if (ocf is not None and capex is not None) else None
    )
    ni_total = (float(ni.dropna().sum()) if ni is not None else None)
    cash_conv = (
        fcf_total / ni_total
        if (fcf_total is not None and ni_total and ni_total > 0)
        else None
    )

    pct = (lambda v: (v / market_cap) if (market_cap and market_cap > 0) else None)

    pct_buybacks   = pct(total_buybacks)
    pct_dividends  = pct(total_dividends)
    pct_capex      = pct(total_capex)
    pct_acq        = pct(total_acquisitions)
    sh_yield       = _annualise_yield(total_returned, years, market_cap)

    inc_roic = _incremental_roic(income, balance)

    score, flags = _score_and_flag(
        incremental_roic=inc_roic,
        buybacks_pct=pct_buybacks,
        cash_conv=cash_conv,
        acquisitions_pct=pct_acq,
    )

    # Per-year DataFrame for the stacked-bar chart
    annual_data = pd.DataFrame(index=cash.index)
    if buybacks is not None:
        annual_data["Buybacks"] = buybacks.abs()
    if dividends is not None:
        annual_data["Dividends"] = dividends.abs()
    if capex is not None:
        annual_data["CapEx"] = capex.abs()
    if acquisitions is not None:
        annual_data["M&A"] = acquisitions.abs()

    return CapitalAllocationResult(
        years=years,
        annual_cf=annual_data,
        totals={
            "buybacks":      total_buybacks,
            "dividends":     total_dividends,
            "capex":         total_capex,
            "acquisitions":  total_acquisitions,
            "fcf":           fcf_total or 0.0,
            "net_income":    ni_total or 0.0,
        },
        as_pct_market_cap={
            "buybacks":      pct_buybacks,
            "dividends":     pct_dividends,
            "capex":         pct_capex,
            "acquisitions":  pct_acq,
        },
        shareholder_yield_annualised=sh_yield,
        incremental_roic=_safe(inc_roic),
        cash_conversion=_safe(cash_conv),
        score=score,
        flags=flags,
    )
