"""
Balance-sheet forensics — goodwill / intangibles / tangible book value
/ leverage / receivables-vs-revenue divergence.

Score starts at 100 and bleeds for each red flag. Inputs are the same
income / balance dataframes the rest of the pipeline already loaded;
no extra fetches.
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
class BalanceSheetQuality:
    score: int                                 # 0-100
    overall: str                               # EXCELLENT / GOOD / MODERATE / POOR
    flag: str                                  # green / yellow / red
    flags: list[tuple[str, str]] = field(default_factory=list)

    total_assets: Optional[float] = None
    goodwill: Optional[float] = None
    goodwill_pct: Optional[float] = None
    intangibles_ex_goodwill: Optional[float] = None
    intangibles_pct: Optional[float] = None
    tangible_book_value: Optional[float] = None
    debt_to_assets: Optional[float] = None
    cash_to_debt: Optional[float] = None
    goodwill_trend: str = "n/a"                # stable | aggressive_ma | writedowns
    receivables_revenue_diff_pp: Optional[float] = None

    interpretation: str = ""


# ============================================================
# Helpers
# ============================================================
def _last(df_or_series, key: Optional[str] = None) -> Optional[float]:
    if isinstance(df_or_series, pd.DataFrame):
        s = _get(df_or_series, key)
    else:
        s = df_or_series
    if s is None:
        return None
    s = s.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _series(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    s = _get(df, key)
    if s is None:
        return None
    s = s.dropna()
    return s if not s.empty else None


def _separate_intangibles(balance: pd.DataFrame) -> tuple[float, float]:
    """Return (goodwill, intangibles_ex_goodwill) for the most recent year."""
    goodwill = _last(balance, "goodwill") or 0.0
    raw_intang = _series(balance, "intangibles")
    if raw_intang is None or raw_intang.empty:
        return goodwill, 0.0

    last_intang = float(raw_intang.iloc[-1])
    # If the alias resolved to the combined "goodwillAndIntangibleAssets"
    # field, we need to subtract goodwill to isolate the residual.
    combined_name = "goodwillAndIntangibleAssets"
    if combined_name in balance.columns and goodwill > 0:
        return goodwill, max(0.0, last_intang - goodwill)
    return goodwill, last_intang


# ============================================================
# Public API
# ============================================================
def analyze_balance_sheet_quality(
    *, income: pd.DataFrame, balance: pd.DataFrame,
) -> Optional[BalanceSheetQuality]:
    if balance is None or balance.empty:
        return None

    total_assets = _last(balance, "total_assets")
    if not total_assets or total_assets <= 0:
        return None

    goodwill, intangibles_ex_gw = _separate_intangibles(balance)

    equity = _last(balance, "total_equity") or 0.0
    total_debt = _last(balance, "total_debt") or 0.0
    cash_eq = _last(balance, "cash_eq") or 0.0

    # Tangible book value
    tangible_bv = equity - goodwill - intangibles_ex_gw

    # Ratios
    gw_pct = goodwill / total_assets if total_assets > 0 else 0.0
    intang_pct = intangibles_ex_gw / total_assets if total_assets > 0 else 0.0
    debt_assets = total_debt / total_assets if total_assets > 0 else 0.0
    cash_debt = (cash_eq / total_debt) if total_debt > 0 else float("inf")

    # Receivables vs revenue divergence (latest YoY)
    rec_rev_diff_pp: Optional[float] = None
    rev_s = _series(income, "revenue")
    rec_s = _series(balance, "receivables")
    if rev_s is not None and rec_s is not None and len(rev_s) >= 2 and len(rec_s) >= 2:
        rev_curr, rev_prev = float(rev_s.iloc[-1]), float(rev_s.iloc[-2])
        rec_curr, rec_prev = float(rec_s.iloc[-1]), float(rec_s.iloc[-2])
        if rev_prev > 0 and rec_prev > 0:
            rev_g = rev_curr / rev_prev - 1
            rec_g = rec_curr / rec_prev - 1
            rec_rev_diff_pp = (rec_g - rev_g) * 100  # in percentage points

    # Goodwill 5y trend
    gw_trend = "stable"
    gw_series = _series(balance, "goodwill")
    if gw_series is not None and len(gw_series) >= 5:
        gw_5y_ago = float(gw_series.iloc[-5])
        if gw_5y_ago > 0:
            ratio = goodwill / gw_5y_ago
            if ratio > 2.0:
                gw_trend = "aggressive_ma"
            elif ratio < 0.7:
                gw_trend = "writedowns"

    # ---- Scoring ----
    score = 100
    flags: list[tuple[str, str]] = []

    # Goodwill % of assets
    if gw_pct > 0.50:
        score -= 30
        flags.append(("✗", f"Goodwill extreme ({gw_pct:.0%} of assets) — high impairment risk"))
    elif gw_pct > 0.40:
        score -= 20
        flags.append(("✗", f"Goodwill very high ({gw_pct:.0%} of assets)"))
    elif gw_pct > 0.25:
        score -= 10
        flags.append(("⚠", f"Goodwill elevated ({gw_pct:.0%} of assets)"))
    elif gw_pct > 0.10:
        flags.append(("ⓘ", f"Goodwill moderate ({gw_pct:.0%} of assets)"))
    else:
        flags.append(("✓", f"Goodwill clean ({gw_pct:.0%} of assets)"))

    if gw_trend == "aggressive_ma":
        score -= 5
        flags.append(("⚠", "Goodwill more than doubled in 5y — aggressive M&A"))
    elif gw_trend == "writedowns":
        score -= 8
        flags.append(("✗", "Goodwill cut sharply in 5y — past writedowns history"))

    # Intangibles ex-goodwill
    if intang_pct > 0.30:
        score -= 10
        flags.append(("⚠", f"Other intangibles high ({intang_pct:.0%}) — soft assets"))

    # Tangible BV
    if tangible_bv < 0:
        score -= 20
        flags.append((
            "✗",
            f"Negative tangible book value (${tangible_bv/1e9:,.1f}B) — equity is intangibles + goodwill",
        ))
    elif equity > 0 and tangible_bv < equity * 0.20:
        score -= 5
        flags.append(("⚠", "Tangible BV is small fraction of total equity"))

    # Receivables outpacing revenue
    if rec_rev_diff_pp is not None and rec_rev_diff_pp > 10:
        score -= 12
        flags.append((
            "⚠",
            f"Receivables growing {rec_rev_diff_pp:+.0f}pp faster than revenue — "
            "earnings-quality concern",
        ))

    # Leverage
    if debt_assets > 0.60:
        score -= 20
        flags.append(("✗", f"Very high leverage ({debt_assets:.0%} debt/assets)"))
    elif debt_assets > 0.40:
        score -= 10
        flags.append(("⚠", f"High leverage ({debt_assets:.0%})"))

    # Cash vs debt
    if cash_debt == float("inf"):
        flags.append(("✓", "No debt outstanding"))
    elif cash_debt > 1.5:
        flags.append(("✓", f"Cash exceeds debt {cash_debt:.1f}× — fortress balance sheet"))
    elif cash_debt < 0.10 and total_debt > 0:
        score -= 8
        flags.append(("⚠", f"Low cash relative to debt ({cash_debt:.2f}×)"))

    score = max(0, min(100, score))

    if score >= 85:
        overall, flag = "EXCELLENT", "green"
    elif score >= 70:
        overall, flag = "GOOD", "green"
    elif score >= 50:
        overall, flag = "MODERATE", "yellow"
    else:
        overall, flag = "POOR", "red"

    interp = _interpret(score, gw_pct, tangible_bv, debt_assets)

    return BalanceSheetQuality(
        score=score,
        overall=overall,
        flag=flag,
        flags=flags,
        total_assets=float(total_assets),
        goodwill=float(goodwill),
        goodwill_pct=float(gw_pct),
        intangibles_ex_goodwill=float(intangibles_ex_gw),
        intangibles_pct=float(intang_pct),
        tangible_book_value=float(tangible_bv),
        debt_to_assets=float(debt_assets),
        cash_to_debt=(float(cash_debt) if cash_debt != float("inf") else None),
        goodwill_trend=gw_trend,
        receivables_revenue_diff_pp=rec_rev_diff_pp,
        interpretation=interp,
    )


def _interpret(score: float, gw_pct: float, tbv: float, debt_a: float) -> str:
    if score >= 85:
        return "Fortress balance sheet — clean intangibles, low debt, ample cash."
    if gw_pct > 0.40:
        return ("Goodwill-heavy balance sheet. Watch for impairments — "
                "writedown risk if acquired businesses underperform.")
    if tbv < 0:
        return ("Negative tangible book value. Equity is essentially intangibles + "
                "goodwill — economic moat had better be real.")
    if debt_a > 0.50:
        return ("Highly leveraged. Cash flow generation needs to comfortably cover "
                "debt service.")
    return "Average balance-sheet quality. No single red flag dominates."
