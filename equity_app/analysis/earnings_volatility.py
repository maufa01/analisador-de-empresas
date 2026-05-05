"""
Earnings volatility — distinguishes compounders from cyclicals.

Five outputs:
    - σ Net Income YoY %                    → volatility of bottom-line growth
    - σ Revenue YoY %                       → volatility of top-line growth
    - σ Net Margin                          → volatility of profit conversion
    - Negative-NI year count                → loss frequency
    - R² of NI linear trend                 → predictability

Plus a profile classification:
    - "Compounder"   — low NI σ, no losses, R² ≥ 0.85
    - "Stable"       — low NI σ, ≤1 loss
    - "Cyclical"     — high NI σ, multiple losses
    - "Volatile"     — high σ + low predictability
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get


@dataclass
class EarningsVolatility:
    profile: str                               # Compounder / Stable / Cyclical / Volatile
    flag: str                                  # green / yellow / red
    score: int                                 # 0-100
    n_years: int

    ni_growth_std_pct: Optional[float] = None
    revenue_growth_std_pct: Optional[float] = None
    net_margin_std_pp: Optional[float] = None
    negative_ni_years: int = 0
    ni_trend_r_squared: Optional[float] = None

    factors: list[tuple[str, str]] = field(default_factory=list)
    interpretation: str = ""


def _series(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    s = _get(df, key)
    if s is None:
        return None
    s = s.dropna()
    return s if not s.empty else None


def analyze_earnings_volatility(*, income: pd.DataFrame) -> Optional[EarningsVolatility]:
    ni_s = _series(income, "net_income")
    rev_s = _series(income, "revenue")
    if ni_s is None or len(ni_s) < 3:
        return None

    n_years = len(ni_s)

    # NI YoY growth (skip if base is non-positive to avoid blowups)
    ni_growth_pct: Optional[pd.Series] = None
    valid = (ni_s.shift(1) > 0)
    if valid.sum() >= 2:
        ni_growth_pct = ((ni_s / ni_s.shift(1) - 1) * 100).where(valid).dropna()

    # Revenue growth
    rev_growth_pct: Optional[pd.Series] = None
    if rev_s is not None and len(rev_s) >= 2:
        rev_growth_pct = (rev_s.pct_change().dropna() * 100)

    # Net margin (NI / revenue)
    net_margin_pp: Optional[pd.Series] = None
    if rev_s is not None:
        common = ni_s.index.intersection(rev_s.index)
        if len(common) >= 3:
            net_margin_pp = (ni_s.loc[common] / rev_s.loc[common] * 100).dropna()

    # Volatilities
    sigma_ni = float(ni_growth_pct.std()) if ni_growth_pct is not None and len(ni_growth_pct) >= 2 else None
    sigma_rev = float(rev_growth_pct.std()) if rev_growth_pct is not None and len(rev_growth_pct) >= 2 else None
    sigma_margin = float(net_margin_pp.std()) if net_margin_pp is not None and len(net_margin_pp) >= 3 else None

    # Negative-NI years
    neg_years = int((ni_s < 0).sum())

    # R² of linear NI trend (only if no losses, otherwise meaningless)
    r2: Optional[float] = None
    if neg_years == 0 and n_years >= 5:
        try:
            from scipy.stats import linregress
            x = np.arange(n_years, dtype=float)
            y = ni_s.values.astype(float)
            _, _, r_value, _, _ = linregress(x, y)
            r2 = float(r_value ** 2)
        except Exception:
            r2 = None

    # ---- Profile classification ----
    factors: list[tuple[str, str]] = []
    score = 50

    if sigma_ni is not None:
        if sigma_ni < 15:
            score += 20
            factors.append(("✓", f"NI growth highly stable (σ={sigma_ni:.1f}%)"))
        elif sigma_ni < 30:
            score += 10
            factors.append(("✓", f"NI growth stable (σ={sigma_ni:.1f}%)"))
        elif sigma_ni > 60:
            score -= 15
            factors.append(("⚠", f"NI growth volatile (σ={sigma_ni:.1f}%)"))

    if sigma_margin is not None:
        if sigma_margin < 1.5:
            score += 10
            factors.append(("✓", f"Net margin very stable (σ={sigma_margin:.1f}pp)"))
        elif sigma_margin > 4.0:
            score -= 8
            factors.append(("⚠", f"Net margin volatile (σ={sigma_margin:.1f}pp)"))

    if neg_years == 0 and n_years >= 5:
        score += 15
        factors.append(("✓", f"No loss years in {n_years}-year window"))
    elif neg_years == 1:
        score += 0
        factors.append(("⚠", "1 loss year"))
    elif neg_years >= 3:
        score -= 15
        factors.append(("✗", f"{neg_years} loss years — cyclical / distressed"))

    if r2 is not None:
        if r2 > 0.85:
            score += 10
            factors.append(("✓", f"NI trajectory highly predictable (R²={r2:.2f})"))
        elif r2 < 0.50:
            factors.append(("⚠", f"NI trajectory unpredictable (R²={r2:.2f})"))

    score = max(0, min(100, score))

    # Profile
    if neg_years == 0 and (sigma_ni is not None and sigma_ni < 20) and (r2 or 0) >= 0.85:
        profile, flag = "Compounder", "green"
        interp = ("Low NI volatility, no loss years, predictable trajectory — "
                  "compounding profile. DCF is the right valuation lens; "
                  "premium multiples are typically justified.")
    elif neg_years <= 1 and (sigma_ni is not None and sigma_ni < 30):
        profile, flag = "Stable", "green"
        interp = ("Stable earnings with limited cyclicality. DCF works; "
                  "use moderate growth expectations.")
    elif neg_years >= 2 or (sigma_ni is not None and sigma_ni > 60):
        profile, flag = "Cyclical", "yellow"
        interp = ("Cyclical earnings — peak / trough multiples mislead. "
                  "Use mid-cycle EPS or normalized earnings; rely on stress "
                  "tests over point estimates.")
    else:
        profile, flag = "Volatile", "yellow"
        interp = ("Volatile but not deeply cyclical. Multiple-based valuations "
                  "should be range-based; DCF is a sketch, not a number.")

    return EarningsVolatility(
        profile=profile,
        flag=flag,
        score=score,
        n_years=n_years,
        ni_growth_std_pct=sigma_ni,
        revenue_growth_std_pct=sigma_rev,
        net_margin_std_pp=sigma_margin,
        negative_ni_years=neg_years,
        ni_trend_r_squared=r2,
        factors=factors,
        interpretation=interp,
    )
