"""
Revenue quality — how predictable, stable, and recurring is the top line.

Five factors, each scored:
    - Gross-margin volatility (σ across years)
    - Operating-margin volatility
    - Revenue-growth volatility (σ of YoY %)
    - Negative-growth years (count over the available window)
    - Trend strength (R² of linear fit on revenue)

Plus one heuristic flag:
    - Sector / industry suggests recurring revenue (software, telecom, …)

Inputs are the same income dataframe the rest of the pipeline already
loaded; the sector/industry strings come from yfinance metadata.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get


# ============================================================
# Result
# ============================================================
@dataclass
class RevenueQuality:
    score: int
    overall: str                               # EXCELLENT / GOOD / AVERAGE / LOW
    flag: str                                  # green / yellow / red
    factors: list[tuple[str, str]] = field(default_factory=list)

    n_years: int = 0
    margin_volatility_gross: Optional[float] = None
    margin_volatility_operating: Optional[float] = None
    growth_volatility: Optional[float] = None
    negative_growth_years: int = 0
    is_likely_recurring: bool = False
    trend_r_squared: Optional[float] = None

    note: str = ""


# ============================================================
# Helpers
# ============================================================
_RECURRING_KEYWORDS = (
    "software", "subscription", "saas", "telecom", "wireless",
    "utility", "utilities", "insurance", "real estate", "asset management",
    "regulated",
)


def _series_clean(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    s = _get(df, key)
    if s is None:
        return None
    s = s.dropna()
    return s if not s.empty else None


# ============================================================
# Public API
# ============================================================
def analyze_revenue_quality(
    *, income: pd.DataFrame,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> Optional[RevenueQuality]:
    rev_s = _series_clean(income, "revenue")
    if rev_s is None or len(rev_s) < 3:
        return None

    n_years = len(rev_s)

    # Gross-margin series
    gp_s = _series_clean(income, "gross_profit")
    gross_margins = (gp_s / rev_s * 100).dropna() if gp_s is not None else None

    # Operating-margin series
    op_s = _series_clean(income, "operating_income")
    op_margins = (op_s / rev_s * 100).dropna() if op_s is not None else None

    # Revenue YoY % growth
    growth_pct = (rev_s.pct_change().dropna() * 100)

    # Volatilities
    sigma_gm = float(gross_margins.std()) if gross_margins is not None and len(gross_margins) >= 3 else None
    sigma_om = float(op_margins.std()) if op_margins is not None and len(op_margins) >= 3 else None
    sigma_growth = float(growth_pct.std()) if len(growth_pct) >= 3 else None

    # Negative-growth years
    neg_years = int((growth_pct < 0).sum())

    # Trend strength (R² of linear fit)
    r2: Optional[float] = None
    if n_years >= 5:
        try:
            from scipy.stats import linregress
            x = np.arange(n_years, dtype=float)
            y = rev_s.values.astype(float)
            slope, intercept, r_value, _, _ = linregress(x, y)
            r2 = float(r_value ** 2)
        except Exception:
            r2 = None

    # Recurring heuristic
    blob = f"{sector or ''} {industry or ''}".lower()
    is_recurring = any(kw in blob for kw in _RECURRING_KEYWORDS)

    # ---- Scoring ----
    score = 50
    factors: list[tuple[str, str]] = []

    if sigma_gm is not None:
        if sigma_gm < 1.5:
            score += 15
            factors.append(("✓", f"Gross margins very stable (σ={sigma_gm:.1f}pp)"))
        elif sigma_gm < 3.0:
            score += 8
            factors.append(("✓", f"Gross margins stable (σ={sigma_gm:.1f}pp)"))
        elif sigma_gm > 5.0:
            score -= 5
            factors.append(("⚠", f"Gross margins volatile (σ={sigma_gm:.1f}pp)"))

    if sigma_om is not None:
        if sigma_om < 2.0:
            score += 10
            factors.append(("✓", "Operating margins highly stable"))
        elif sigma_om > 5.0:
            score -= 5
            factors.append(("⚠", f"Operating margins volatile (σ={sigma_om:.1f}pp)"))

    if sigma_growth is not None:
        if sigma_growth < 5:
            score += 15
            factors.append(("✓", f"Highly consistent revenue growth (σ={sigma_growth:.1f}%)"))
        elif sigma_growth < 15:
            score += 8
            factors.append(("✓", f"Reasonable consistency (σ={sigma_growth:.1f}%)"))
        elif sigma_growth > 25:
            score -= 8
            factors.append(("⚠", f"Volatile growth (σ={sigma_growth:.1f}%)"))

    if is_recurring:
        score += 10
        factors.append(("✓", f"Sector/industry suggests recurring revenue ({industry or sector})"))

    if neg_years == 0 and n_years >= 5:
        score += 15
        factors.append(("✓", f"No revenue declines in {n_years} years — strong moat"))
    elif neg_years == 1:
        score += 5
        factors.append(("✓", "Only 1 year of revenue decline"))
    elif neg_years >= 3:
        score -= 10
        factors.append(("✗", f"{neg_years} years of revenue decline"))

    if r2 is not None:
        if r2 > 0.90:
            score += 10
            factors.append(("✓", f"Very predictable trajectory (R²={r2:.2f})"))
        elif r2 < 0.50:
            factors.append(("⚠", f"Weak trend, hard to forecast (R²={r2:.2f})"))

    score = max(0, min(100, score))

    if score >= 80:
        overall, flag = "EXCELLENT", "green"
    elif score >= 65:
        overall, flag = "GOOD", "green"
    elif score >= 45:
        overall, flag = "AVERAGE", "yellow"
    else:
        overall, flag = "LOW", "red"

    note = ""
    if n_years < 5:
        note = (f"Only {n_years} years of revenue history available — "
                "recurring vs transactional mix and customer concentration "
                "require segment data (FMP).")
    else:
        note = ("Customer concentration & recurring/transactional split "
                "require segment data (FMP). Estimated from sector heuristic.")

    return RevenueQuality(
        score=score,
        overall=overall,
        flag=flag,
        factors=factors,
        n_years=n_years,
        margin_volatility_gross=sigma_gm,
        margin_volatility_operating=sigma_om,
        growth_volatility=sigma_growth,
        negative_growth_years=neg_years,
        is_likely_recurring=is_recurring,
        trend_r_squared=r2,
        note=note,
    )
