"""
Sector-aware sub-scoring for equity analysis.

Maps the raw fundamentals + valuation outputs into five 0-100 sub-scores
(growth, profitability, solvency, earnings quality, valuation), then
combines them with the weights in ``SCORING_WEIGHTS``.

Each sub-score uses a piecewise-linear mapping calibrated on common
S&P 500 ranges — e.g. revenue CAGR of 0% scores ~30, 10% scores ~70,
25%+ caps at 95. The functions are intentionally simple so the whole
pipeline is auditable and easy to override per sector when that becomes
relevant.

Inputs are loose: every kwarg is optional. Missing data simply omits a
sub-score; the surviving weights are renormalised.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.earnings_quality import EarningsQuality
from analysis.ratios import _get, cagr, free_cash_flow
from core.constants import SCORING_WEIGHTS


# ============================================================
# Result
# ============================================================
@dataclass
class ScoreBreakdown:
    growth: Optional[float] = None
    profitability: Optional[float] = None
    solvency: Optional[float] = None
    earnings_quality: Optional[float] = None
    valuation: Optional[float] = None

    composite: float = 0.0
    weights_used: dict[str, float] = field(default_factory=dict)
    explanations: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Optional[float]]:
        return {
            "Growth": self.growth,
            "Profitability": self.profitability,
            "Solvency": self.solvency,
            "Earnings quality": self.earnings_quality,
            "Valuation": self.valuation,
            "Composite": self.composite,
        }


# ============================================================
# Mapping helpers — piecewise linear 0-100
# ============================================================
def _piecewise(value: float, anchors: list[tuple[float, float]]) -> float:
    """
    Linearly interpolate ``value`` over a sorted anchor list of
    (input, score) pairs. Below the smallest anchor → first score;
    above the largest → last score.
    """
    if value is None or not np.isfinite(value):
        return float("nan")
    xs = [a[0] for a in anchors]
    ys = [a[1] for a in anchors]
    if value <= xs[0]:
        return ys[0]
    if value >= xs[-1]:
        return ys[-1]
    return float(np.interp(value, xs, ys))


def _clip(score: Optional[float]) -> Optional[float]:
    if score is None or not np.isfinite(score):
        return None
    return float(np.clip(score, 0.0, 100.0))


# ============================================================
# Sub-scores
# ============================================================
def score_growth(
    income: pd.DataFrame, cash: pd.DataFrame
) -> tuple[Optional[float], str]:
    """Average score across revenue / EPS / FCF 5y CAGR."""
    rev = _get(income, "revenue")
    eps = _get(income, "eps")
    fcf = free_cash_flow(cash)

    cagrs = []
    for s in (rev, eps, fcf):
        if s is None:
            continue
        clean = s.dropna()
        if len(clean) < 2:
            continue
        c = cagr(clean, periods=min(5, len(clean) - 1))
        if np.isfinite(c):
            cagrs.append(c)
    if not cagrs:
        return None, "Insufficient growth data"

    g_avg = float(np.mean(cagrs))
    score = _piecewise(g_avg, [
        (-0.20, 0), (-0.05, 25), (0.0, 40), (0.05, 60),
        (0.10, 75), (0.20, 90), (0.30, 100),
    ])
    return _clip(score), f"Avg CAGR {g_avg:.1%} across rev/EPS/FCF"


def score_profitability(income: pd.DataFrame, balance: pd.DataFrame) -> tuple[Optional[float], str]:
    """Combination of ROE and operating margin (latest year)."""
    ni = _get(income, "net_income")
    eq = _get(balance, "total_equity")
    rev = _get(income, "revenue")
    op  = _get(income, "operating_income")

    parts = []
    drivers = []
    if ni is not None and eq is not None:
        df = pd.concat([ni, eq], axis=1).dropna().tail(1)
        if not df.empty and df.iloc[0, 1] > 0:
            roe = float(df.iloc[0, 0] / df.iloc[0, 1])
            parts.append(_piecewise(roe, [
                (-0.10, 0), (0.0, 25), (0.05, 40), (0.10, 60),
                (0.18, 80), (0.30, 95), (0.50, 100),
            ]))
            drivers.append(f"ROE {roe:.1%}")
    if op is not None and rev is not None:
        df = pd.concat([op, rev], axis=1).dropna().tail(1)
        if not df.empty and df.iloc[0, 1] > 0:
            om = float(df.iloc[0, 0] / df.iloc[0, 1])
            parts.append(_piecewise(om, [
                (-0.20, 0), (0.0, 30), (0.05, 50), (0.10, 65),
                (0.20, 80), (0.30, 90), (0.40, 100),
            ]))
            drivers.append(f"Op. margin {om:.1%}")

    if not parts:
        return None, "Insufficient profitability data"
    return _clip(float(np.mean(parts))), " · ".join(drivers)


def score_solvency(income: pd.DataFrame, balance: pd.DataFrame) -> tuple[Optional[float], str]:
    """Debt/Equity + interest coverage. Lower D/E and higher coverage ⇒ better."""
    debt = _get(balance, "total_debt")
    eq = _get(balance, "total_equity")
    op = _get(income, "operating_income")
    interest = _get(income, "interest_expense")

    parts = []
    drivers = []
    if debt is not None and eq is not None:
        df = pd.concat([debt, eq], axis=1).dropna().tail(1)
        if not df.empty and df.iloc[0, 1] > 0:
            de = float(df.iloc[0, 0] / df.iloc[0, 1])
            parts.append(_piecewise(de, [
                (0.0, 100), (0.5, 85), (1.0, 70),
                (1.5, 55), (2.5, 35), (4.0, 15), (6.0, 0),
            ]))
            drivers.append(f"D/E {de:.2f}")
    if op is not None and interest is not None:
        df = pd.concat([op, interest], axis=1).dropna().tail(1)
        if not df.empty and df.iloc[0, 1] > 0:
            cov = float(df.iloc[0, 0] / df.iloc[0, 1])
            parts.append(_piecewise(cov, [
                (0.5, 0), (1.5, 25), (3.0, 50), (5.0, 70),
                (10.0, 85), (20.0, 100),
            ]))
            drivers.append(f"Int. coverage {cov:.1f}×")

    if not parts:
        return None, "Insufficient solvency data"
    return _clip(float(np.mean(parts))), " · ".join(drivers)


def score_earnings_quality(eq: Optional[EarningsQuality]) -> tuple[Optional[float], str]:
    """Map the worst-of flag to a 0-100 score."""
    if eq is None:
        return None, "Earnings quality not assessed"
    flag = eq.overall_flag
    score = {"green": 85.0, "yellow": 55.0, "red": 25.0, "unknown": 50.0}.get(flag, 50.0)
    return score, f"Overall flag: {flag.upper()}"


def score_valuation(
    *,
    intrinsic: Optional[float],
    current_price: Optional[float],
) -> tuple[Optional[float], str]:
    """Map upside vs aggregator-intrinsic to 0-100."""
    if intrinsic is None or current_price is None or current_price <= 0:
        return None, "No valuation upside available"
    upside = (intrinsic - current_price) / current_price
    score = _piecewise(upside, [
        (-0.50, 0), (-0.30, 15), (-0.15, 35), (0.0, 50),
        (0.10, 65), (0.30, 85), (0.50, 95), (1.00, 100),
    ])
    return _clip(score), f"Upside {upside:+.1%} vs aggregator intrinsic"


# ============================================================
# Composite
# ============================================================
def compute_score(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    earnings_quality: Optional[EarningsQuality] = None,
    intrinsic: Optional[float] = None,
    current_price: Optional[float] = None,
) -> ScoreBreakdown:
    g, g_expl = score_growth(income, cash)
    p, p_expl = score_profitability(income, balance)
    s, s_expl = score_solvency(income, balance)
    eq_score, eq_expl = score_earnings_quality(earnings_quality)
    v, v_expl = score_valuation(intrinsic=intrinsic, current_price=current_price)

    parts: dict[str, Optional[float]] = {
        "growth":           g,
        "profitability":    p,
        "solvency":         s,
        "earnings_quality": eq_score,
        "valuation":        v,
    }
    survivors = {k: v_ for k, v_ in parts.items() if v_ is not None}

    if not survivors:
        composite = 0.0
        renorm: dict[str, float] = {}
    else:
        raw_w = {k: SCORING_WEIGHTS.get(k, 0.0) for k in survivors}
        total = sum(raw_w.values()) or 1.0
        renorm = {k: raw_w[k] / total for k in survivors}
        composite = float(sum(renorm[k] * survivors[k] for k in survivors))

    return ScoreBreakdown(
        growth=g, profitability=p, solvency=s,
        earnings_quality=eq_score, valuation=v,
        composite=composite,
        weights_used=renorm,
        explanations={
            "growth": g_expl, "profitability": p_expl, "solvency": s_expl,
            "earnings_quality": eq_expl, "valuation": v_expl,
        },
    )
