"""
Dividend safety scoring — 0-100 probability that the dividend survives.

Inputs are already-fetched income / balance / cash dataframes (FMP /
yfinance shape, accessed via ``ratios._get`` aliases). Returns a single
``DividendSafetyResult`` with the score, flag, and the ``(symbol, message)``
flag list the UI uses to explain *why*.

Five-pillar weighting:
    - Payout ratio (NI-based)        25 pts
    - FCF coverage                   25 pts
    - Consecutive growth years       20 pts
    - Cash-on-hand coverage          15 pts
    - Leverage support               15 pts
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow


# ============================================================
# Result
# ============================================================
@dataclass
class DividendSafetyResult:
    applicable: bool
    score: int                                 # 0-100
    overall: str                               # VERY SAFE / SAFE / MODERATE / AT RISK / HIGH RISK
    flag: str                                  # green / yellow / red
    flags: list[tuple[str, str]] = field(default_factory=list)   # (symbol, msg)

    annual_dividend: Optional[float] = None
    payout_ratio_ni: Optional[float] = None
    payout_ratio_fcf: Optional[float] = None
    fcf_coverage: Optional[float] = None
    consecutive_growth_years: int = 0
    cash_coverage_years: Optional[float] = None
    debt_to_equity: Optional[float] = None
    div_growth_5y: Optional[float] = None

    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    note: str = ""


# ============================================================
# Helpers
# ============================================================
def _last_value(s: Optional[pd.Series]) -> Optional[float]:
    if s is None:
        return None
    s = s.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _dividends_paid(cash: pd.DataFrame) -> Optional[pd.Series]:
    """Annual dividends paid — absolute value, indexed ascending."""
    raw = _get(cash, "dividends_paid")
    if raw is None:
        return None
    s = raw.dropna()
    if s.empty:
        return None
    return s.abs()


def _consecutive_growth(div_series: pd.Series) -> int:
    """Counted from the most recent year backwards while strictly increasing."""
    s = div_series.dropna()
    if len(s) < 2:
        return 0
    # series is ascending — walk from end backwards
    streak = 0
    for i in range(len(s) - 1, 0, -1):
        if s.iloc[i] > s.iloc[i - 1]:
            streak += 1
        else:
            break
    return streak


# ============================================================
# Public API
# ============================================================
def analyze_dividend_safety(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
) -> DividendSafetyResult:
    div_series = _dividends_paid(cash)
    if div_series is None or div_series.iloc[-1] <= 0:
        return DividendSafetyResult(
            applicable=False, score=0, overall="N/A", flag="unknown",
            note="Company does not pay material dividends.",
        )

    annual_div = float(div_series.iloc[-1])

    # Net income / OCF / FCF
    ni = _last_value(_get(income, "net_income"))
    fcf_series = free_cash_flow(cash)
    fcf = _last_value(fcf_series)

    # Balance sheet pillars
    cash_eq = _last_value(_get(balance, "cash_eq"))
    total_debt = _last_value(_get(balance, "total_debt")) or 0.0
    equity = _last_value(_get(balance, "total_equity"))

    # Ratios
    payout_ni = (annual_div / ni) if (ni and ni > 0) else None
    payout_fcf = (annual_div / fcf) if (fcf and fcf > 0) else None
    fcf_coverage = (fcf / annual_div) if (fcf and annual_div > 0) else None
    cash_cov = (cash_eq / annual_div) if (cash_eq and annual_div > 0) else None
    de = (total_debt / equity) if (equity and equity > 0) else None

    # Growth track record
    streak = _consecutive_growth(div_series)
    div_growth_5y: Optional[float] = None
    if len(div_series.dropna()) >= 5:
        s5 = div_series.dropna().tail(5)
        if s5.iloc[0] > 0:
            div_growth_5y = float((s5.iloc[-1] / s5.iloc[0]) ** (1 / 4) - 1)

    # ---- Scoring ----
    score = 0
    flags: list[tuple[str, str]] = []

    # Payout ratio (NI) — 25 pts
    if payout_ni is None:
        flags.append(("⚠", "Payout ratio could not be computed (Net income missing or non-positive)"))
    elif payout_ni < 0.30:
        score += 25
        flags.append(("✓", f"Payout ratio very low ({payout_ni:.0%}) — heavy retention"))
    elif payout_ni < 0.50:
        score += 18
        flags.append(("✓", f"Payout ratio healthy ({payout_ni:.0%})"))
    elif payout_ni < 0.70:
        score += 10
        flags.append(("⚠", f"Payout ratio elevated ({payout_ni:.0%})"))
    elif payout_ni < 1.0:
        score += 3
        flags.append(("⚠", f"Payout ratio high ({payout_ni:.0%})"))
    else:
        flags.append(("✗", f"Payout ratio > 100% ({payout_ni:.0%}) — paying more than earning"))

    # FCF coverage — 25 pts
    if fcf_coverage is None:
        flags.append(("⚠", "FCF coverage unavailable (FCF missing or non-positive)"))
    elif fcf_coverage > 3.0:
        score += 25
        flags.append(("✓", f"FCF covers dividends {fcf_coverage:.1f}× — fortress"))
    elif fcf_coverage > 2.0:
        score += 18
        flags.append(("✓", f"FCF covers dividends {fcf_coverage:.1f}× — safe"))
    elif fcf_coverage > 1.5:
        score += 12
        flags.append(("✓", f"FCF covers dividends {fcf_coverage:.1f}×"))
    elif fcf_coverage > 1.0:
        score += 5
        flags.append(("⚠", f"FCF barely covers ({fcf_coverage:.1f}×)"))
    else:
        flags.append(("✗", f"FCF does NOT cover dividends ({fcf_coverage:.1f}×) — unsustainable"))

    # Growth track record — 20 pts
    if streak >= 5:
        score += 20
        flags.append(("✓", f"{streak} consecutive years of growth"))
    elif streak >= 3:
        score += 12
        flags.append(("✓", f"{streak} consecutive years of growth"))
    elif streak >= 1:
        score += 5
        flags.append(("⚠", f"Only {streak} year of growth"))
    else:
        flags.append(("✗", "No recent dividend growth"))

    # Cash coverage — 15 pts
    if cash_cov is None:
        flags.append(("⚠", "Cash coverage unavailable"))
    elif cash_cov > 5:
        score += 15
        flags.append(("✓", f"Cash on hand covers {cash_cov:.1f} years of dividends"))
    elif cash_cov > 2:
        score += 10
        flags.append(("✓", f"Cash covers {cash_cov:.1f} years"))
    elif cash_cov > 1:
        score += 5
        flags.append(("⚠", f"Cash covers only {cash_cov:.1f} year"))
    else:
        flags.append(("⚠", f"Cash on hand under 1× annual dividend"))

    # Leverage — 15 pts
    if de is None:
        flags.append(("⚠", "Debt/Equity unavailable"))
    elif de < 0.5:
        score += 15
        flags.append(("✓", f"Low leverage (D/E {de:.2f}) supports dividend"))
    elif de < 1.5:
        score += 8
        flags.append(("✓", f"Moderate leverage (D/E {de:.2f})"))
    elif de < 3.0:
        score += 3
        flags.append(("⚠", f"Elevated leverage (D/E {de:.2f})"))
    else:
        flags.append(("✗", f"Very high leverage (D/E {de:.2f}) threatens dividend"))

    score = max(0, min(100, score))

    # Overall flag
    if score >= 80:
        overall, flag = "VERY SAFE", "green"
    elif score >= 60:
        overall, flag = "SAFE", "green"
    elif score >= 40:
        overall, flag = "MODERATE RISK", "yellow"
    elif score >= 20:
        overall, flag = "AT RISK", "yellow"
    else:
        overall, flag = "HIGH RISK OF CUT", "red"

    # History as DataFrame for the chart
    hist = pd.DataFrame({"dividends_paid": div_series.dropna()})

    return DividendSafetyResult(
        applicable=True,
        score=score,
        overall=overall,
        flag=flag,
        flags=flags,
        annual_dividend=annual_div,
        payout_ratio_ni=payout_ni,
        payout_ratio_fcf=payout_fcf,
        fcf_coverage=fcf_coverage,
        consecutive_growth_years=streak,
        cash_coverage_years=cash_cov,
        debt_to_equity=de,
        div_growth_5y=div_growth_5y,
        history=hist,
    )


# ============================================================
# Educational comparison — historical dividend cuts
# ============================================================
DIVIDEND_CUTS_HISTORICAL: list[dict] = [
    {"ticker": "T",   "year": 2022, "payout_ni": 1.15, "fcf_cov": 0.9, "score": 28, "outcome": "Cut 50%"},
    {"ticker": "GE",  "year": 2017, "payout_ni": 0.95, "fcf_cov": 0.7, "score": 22, "outcome": "Cut 50%"},
    {"ticker": "WFC", "year": 2020, "payout_ni": 0.45, "fcf_cov": 1.4, "score": 58, "outcome": "Cut 80% (regulatory)"},
    {"ticker": "DIS", "year": 2020, "payout_ni": 1.20, "fcf_cov": 0.5, "score": 18, "outcome": "Suspended"},
    {"ticker": "BA",  "year": 2020, "payout_ni": 0.85, "fcf_cov": -0.3, "score": 12, "outcome": "Suspended"},
]
