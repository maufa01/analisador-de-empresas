"""
Working-capital efficiency analysis — Cash Conversion Cycle (CCC).

CCC = DSO + DIO − DPO

    DSO = Receivables  /  Revenue × 365   (days to collect)
    DIO = Inventory    /  COGS    × 365   (days inventory sits)
    DPO = Payables     /  COGS    × 365   (days to pay suppliers)

A negative CCC means the company collects from customers before
paying suppliers (Apple, Amazon) — self-funding growth. A high
positive CCC means cash is trapped in inventory and receivables.

Operates on the same FMP-shape DataFrames the rest of the analysis
layer uses. Industry comparison delegates to the Damodaran loader
when present, falling back to a sane default when missing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import math
import numpy as np
import pandas as pd

from analysis.ratios import _get


@dataclass
class CCCResult:
    current_ccc: Optional[float]
    current_dso: Optional[float]
    current_dio: Optional[float]
    current_dpo: Optional[float]
    avg_5y_ccc: Optional[float]
    industry_avg_ccc: Optional[float]
    yoy_change: Optional[float]
    trend: str                                       # "improving" | "stable" | "deteriorating"
    is_negative_ccc: bool
    score: int                                       # 0-100
    interpretation: str
    history: pd.DataFrame = field(default_factory=pd.DataFrame)


# ============================================================
# Internals
# ============================================================
def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    try:
        if b == 0 or not math.isfinite(b):
            return None
        out = a / b
    except (TypeError, ZeroDivisionError):
        return None
    return out if math.isfinite(out) else None


def _last(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _slope_trend(series: pd.Series) -> str:
    s = series.dropna()
    if len(s) < 3:
        return "insufficient data"
    try:
        from scipy.stats import linregress
        x = np.arange(len(s))
        slope, _, _, _, _ = linregress(x, s.values)
    except Exception:
        slope = float(s.iloc[-1] - s.iloc[0]) / max(len(s) - 1, 1)
    if abs(slope) < 0.5:
        return "stable"
    return "improving" if slope < 0 else "deteriorating"


def _interpret(ccc: Optional[float], industry: Optional[float], trend: str) -> str:
    if ccc is None:
        return ("CCC not computable — accounts payable or COGS missing "
                "from the financials.")
    if ccc < 0:
        return ("**Negative CCC** — the company collects from customers "
                "before paying suppliers. Best-in-class capital efficiency: "
                "growth is self-funded by float from the working-capital cycle.")
    if industry is None:
        return f"CCC of {ccc:.0f} days. Trend: {trend}."
    if ccc < industry * 0.7:
        return (f"Top-quartile efficiency. CCC of **{ccc:.0f} days** is well "
                f"below the industry median (~{industry:.0f} days).")
    if ccc > industry * 1.3:
        return (f"Below-average efficiency. CCC of **{ccc:.0f} days** is "
                f"materially above the industry median (~{industry:.0f} days). "
                "Investigate whether inventory turns or receivables collection "
                "are deteriorating.")
    return (f"In line with industry (~{industry:.0f} days). "
            f"Trend over the last few years is **{trend}**.")


def _score(
    ccc: Optional[float],
    industry: Optional[float],
    trend: str,
) -> int:
    if ccc is None:
        return 50
    if ccc < 0:
        base = 95
    elif industry is None:
        base = 70 if ccc < 30 else 55 if ccc < 60 else 40
    elif ccc < industry * 0.5:
        base = 85
    elif ccc < industry * 1.0:
        base = 70
    elif ccc < industry * 1.5:
        base = 50
    else:
        base = 30
    if trend == "improving":
        base += 10
    elif trend == "deteriorating":
        base -= 10
    return int(np.clip(base, 0, 100))


# ============================================================
# Public API
# ============================================================
def compute_ccc_history(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
) -> pd.DataFrame:
    """Returns a DataFrame indexed by period with DSO, DIO, DPO, CCC columns."""
    if income.empty or balance.empty:
        return pd.DataFrame()

    rev   = _get(income, "revenue")
    cogs  = _get(income, "cost_of_revenue")
    rec   = _get(balance, "receivables")
    inv   = _get(balance, "inventory")
    # Accounts payable is rarely surfaced as a direct alias in our ratios
    # module — fall back to current_liabilities as a proxy if missing.
    ap_alias = (
        balance.get("accountPayables")
        if "accountPayables" in balance.columns
        else None
    )
    if ap_alias is None:
        ap_alias = _get(balance, "current_liabilities")

    if rev is None or rec is None or inv is None or ap_alias is None or cogs is None:
        return pd.DataFrame()

    df = pd.concat([rev, cogs, rec, inv, ap_alias], axis=1).dropna()
    df.columns = ["rev", "cogs", "rec", "inv", "ap"]
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)
    out["DSO"] = (df["rec"] / df["rev"] * 365.0).where(df["rev"] > 0)
    out["DIO"] = (df["inv"] / df["cogs"] * 365.0).where(df["cogs"] > 0)
    out["DPO"] = (df["ap"]  / df["cogs"] * 365.0).where(df["cogs"] > 0)
    out["CCC"] = out["DSO"] + out["DIO"] - out["DPO"]
    return out.sort_index()


def analyze_ccc(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    sector: Optional[str] = None,
) -> CCCResult:
    """Full CCC analysis — current values + 5y avg + trend + score + interpretation."""
    history = compute_ccc_history(income=income, balance=balance)

    if history.empty or history["CCC"].dropna().empty:
        return CCCResult(
            current_ccc=None, current_dso=None, current_dio=None,
            current_dpo=None, avg_5y_ccc=None, industry_avg_ccc=None,
            yoy_change=None, trend="insufficient data",
            is_negative_ccc=False,
            score=50,
            interpretation=_interpret(None, None, "insufficient data"),
            history=history,
        )

    current_ccc = _last(history["CCC"])
    avg_5y = float(history["CCC"].dropna().tail(5).mean())
    trend = _slope_trend(history["CCC"])

    # YoY change
    ccc_clean = history["CCC"].dropna()
    yoy_change = (
        float(ccc_clean.iloc[-1] - ccc_clean.iloc[-2])
        if len(ccc_clean) >= 2 else None
    )

    # Industry comparison via the Damodaran loader (asset turnover proxy
    # converts roughly to CCC inverse — we just look up a curated value).
    industry_avg: Optional[float] = None
    try:
        from analysis.damodaran_loader import get_industry_benchmarks
        bench = get_industry_benchmarks(industry=None, sector=sector)
        # No direct CCC field in Damodaran — use sector heuristic.
        # Tech/services typically run ~30-50 days; staples ~50-70.
    except Exception:
        bench = {}
    industry_avg = {
        "Technology":             45.0,
        "Healthcare":             80.0,
        "Financial Services":     None,        # banks: not meaningful
        "Consumer Discretionary": 55.0,
        "Consumer Staples":       50.0,
        "Industrials":            70.0,
        "Energy":                 40.0,
        "Materials":              80.0,
        "Real Estate":            None,
        "Utilities":              None,
        "Communication Services": 50.0,
    }.get(sector) if sector else None

    score = _score(current_ccc, industry_avg, trend)
    interpretation = _interpret(current_ccc, industry_avg, trend)

    return CCCResult(
        current_ccc=current_ccc,
        current_dso=_last(history["DSO"]),
        current_dio=_last(history["DIO"]),
        current_dpo=_last(history["DPO"]),
        avg_5y_ccc=avg_5y,
        industry_avg_ccc=industry_avg,
        yoy_change=yoy_change,
        trend=trend,
        is_negative_ccc=(current_ccc is not None and current_ccc < 0),
        score=score,
        interpretation=interpretation,
        history=history,
    )
