"""
Unified quality-assessment facade.

This is the single public entry point for all quality checks. It
re-exports the dataclasses + functions that previously lived in 4
separate modules:

- ``earnings_quality``     → Beneish / Piotroski / Sloan
- ``balance_sheet_quality`` → goodwill / TBV / leverage forensic flags
- ``revenue_quality``       → margin volatility / recurring-revenue heuristic
- ``fundamentals_check``    → coherence checks (BS identity, cash recon)

The implementations stay in their original modules — Python's lazy
import means no startup-time cost vs a single mega-module, and the
facade keeps the original files importable so existing callers don't
break. New callers should prefer this module.

The :func:`assess_all_quality` helper runs every check and aggregates
into one :class:`QualityReport` with a worst-of overall flag + average
score.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ============================================================
# Re-exports — dataclasses + key functions
# ============================================================
from analysis.earnings_quality import (
    EarningsQuality, QualityFlag,
    beneish_m_score, piotroski_f_score, sloan_ratio,
    assess_earnings_quality,
)
from analysis.balance_sheet_quality import (
    BalanceSheetQuality, analyze_balance_sheet_quality,
)
from analysis.revenue_quality import (
    RevenueQuality, analyze_revenue_quality,
)
from analysis.fundamentals_check import (
    Issue, CoherenceReport, coherence_report,
    check_balance_sheet_identity, check_cash_reconciliation,
    check_index_integrity, check_critical_fields, check_sign_sanity,
)


# ============================================================
# Unified report
# ============================================================
@dataclass
class QualityReport:
    """Aggregated quality assessment across all 4 check categories."""
    earnings:     Optional[EarningsQuality]
    balance:      Optional[BalanceSheetQuality]
    revenue:      Optional[RevenueQuality]
    completeness: Optional[CoherenceReport]
    overall_flag: str          # "green" | "yellow" | "red" | "unknown"
    overall_score: float       # 0-100, average of populated sub-scores


# ============================================================
# Public API
# ============================================================
def assess_all_quality(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> QualityReport:
    """Run every quality assessment and return the aggregated report.

    Worst-of flag rule: any RED → red, any YELLOW → yellow, all GREEN
    → green, no signal at all → unknown. Score is the simple mean of
    available sub-scores (Beneish/Piotroski/Sloan share the EarningsQuality
    container, so its mean is taken first as a single sub-score).
    """
    eq = analyze_earnings_or_none(income, balance, cash)
    bs = analyze_balance_or_none(balance)
    rv = analyze_revenue_or_none(income)
    coh = analyze_completeness_or_none(income, balance, cash)

    flag_pool: list[str] = []
    if eq is not None:
        flag_pool.append(eq.overall_flag)
    if bs is not None:
        flag_pool.append(bs.flag)
    if rv is not None:
        flag_pool.append(rv.flag)

    if not flag_pool:
        overall_flag = "unknown"
    elif any(f == "red" for f in flag_pool):
        overall_flag = "red"
    elif any(f == "yellow" for f in flag_pool):
        overall_flag = "yellow"
    else:
        overall_flag = "green"

    # Average available sub-scores. EarningsQuality scores are M-score-style
    # numbers, not 0-100, so we skip those — only balance + revenue
    # contribute on the canonical 0-100 scale.
    sub_scores: list[float] = []
    if bs is not None:
        sub_scores.append(float(bs.score))
    if rv is not None:
        sub_scores.append(float(rv.score))
    overall_score = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0

    return QualityReport(
        earnings=eq,
        balance=bs,
        revenue=rv,
        completeness=coh,
        overall_flag=overall_flag,
        overall_score=overall_score,
    )


# ============================================================
# Helpers — return None instead of raising on bad input
# ============================================================
def analyze_earnings_or_none(
    income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
) -> Optional[EarningsQuality]:
    try:
        return assess_earnings_quality(income, balance, cash)
    except Exception:
        return None


def analyze_balance_or_none(balance: pd.DataFrame) -> Optional[BalanceSheetQuality]:
    try:
        return analyze_balance_sheet_quality(balance=balance)
    except Exception:
        return None


def analyze_revenue_or_none(income: pd.DataFrame) -> Optional[RevenueQuality]:
    try:
        return analyze_revenue_quality(income=income)
    except Exception:
        return None


def analyze_completeness_or_none(
    income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
) -> Optional[CoherenceReport]:
    try:
        return coherence_report(income=income, balance=balance, cash=cash)
    except Exception:
        return None


__all__ = [
    # Aggregated report
    "QualityReport", "assess_all_quality",

    # Earnings (Beneish / Piotroski / Sloan)
    "EarningsQuality", "QualityFlag",
    "beneish_m_score", "piotroski_f_score", "sloan_ratio",
    "assess_earnings_quality",

    # Balance-sheet forensics
    "BalanceSheetQuality", "analyze_balance_sheet_quality",

    # Revenue quality
    "RevenueQuality", "analyze_revenue_quality",

    # Fundamentals coherence
    "Issue", "CoherenceReport", "coherence_report",
    "check_balance_sheet_identity", "check_cash_reconciliation",
    "check_index_integrity", "check_critical_fields", "check_sign_sanity",
]
