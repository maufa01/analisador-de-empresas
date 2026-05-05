"""
Insider activity (Form 4) — net buying / selling, cluster detection,
CEO + CFO segregation, sentiment score 0-100.

Source: ``data.fmp_extras.fetch_insider_transactions`` — returns empty
when ``FMP_API_KEY`` isn't configured. The analysis dataclass exposes
``available=False`` in that case so the UI renders the "configure FMP"
empty state without crashing.

Why no fallback to yfinance: yfinance does NOT expose Form-4 data
reliably — the ``insider_transactions`` attribute either errors or
returns garbage on most tickers. Better to honestly say "FMP required".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# Result types
# ============================================================
@dataclass
class ClusterEvent:
    start_date: pd.Timestamp
    end_date:   pd.Timestamp
    n_insiders: int
    total_value_usd: float
    insider_names: list[str]


@dataclass
class ExecutiveActivity:
    role:            str                    # "CEO" or "CFO"
    n_transactions:  int
    n_buys:          int
    n_sells:         int
    net_value_usd:   float


@dataclass
class InsiderActivity:
    available: bool
    flag:      str                              # green / yellow / red / unknown
    score:     int                              # 0-100
    interpretation: str = ""

    n_transactions: int = 0
    n_purchases:    int = 0
    n_sales:        int = 0
    n_awards:       int = 0
    total_bought_usd: float = 0.0
    total_sold_usd:   float = 0.0
    net_activity_usd: float = 0.0

    recent_6m_net_usd:  float = 0.0
    prior_6m_net_usd:   float = 0.0
    trend:              str = "—"               # increasing / stable / decreasing

    clusters:    list[ClusterEvent] = field(default_factory=list)
    ceo:         Optional[ExecutiveActivity] = None
    cfo:         Optional[ExecutiveActivity] = None

    raw:         pd.DataFrame = field(default_factory=pd.DataFrame)
    note:        str = ""


# ============================================================
# Helpers
# ============================================================
def _is_buy(row: pd.Series) -> bool:
    s = str(row.get("transactionType", ""))
    return s.startswith("P") or "Purchase" in s


def _is_sell(row: pd.Series) -> bool:
    s = str(row.get("transactionType", ""))
    return s.startswith("S") or "Sale" in s


def _is_award(row: pd.Series) -> bool:
    s = str(row.get("transactionType", ""))
    return s.startswith("A") or "Award" in s


def _net_value(df: pd.DataFrame) -> float:
    if df.empty or "transaction_value" not in df.columns:
        return 0.0
    buys = df[df.apply(_is_buy, axis=1)]["transaction_value"].sum()
    sells = df[df.apply(_is_sell, axis=1)]["transaction_value"].sum()
    return float(buys - sells)


def _detect_clusters(
    purchases: pd.DataFrame,
    *, window_days: int = 30, min_insiders: int = 3,
) -> list[ClusterEvent]:
    """Slide a 30-day window over insider purchases, dedup overlapping
    windows so two clusters don't get reported for the same buying spree."""
    if purchases.empty or "transactionDate" not in purchases.columns:
        return []
    df = purchases.dropna(subset=["transactionDate"]).sort_values("transactionDate")
    if df.empty:
        return []

    clusters: list[ClusterEvent] = []
    last_cluster_end: Optional[pd.Timestamp] = None
    for _, row in df.iterrows():
        start = pd.Timestamp(row["transactionDate"])
        # Skip windows that fall inside a cluster we already recorded
        if last_cluster_end is not None and start <= last_cluster_end:
            continue
        end = start + pd.Timedelta(days=window_days)
        window = df[(df["transactionDate"] >= start)
                    & (df["transactionDate"] <= end)]
        unique_names = window["reportingName"].dropna().unique() if "reportingName" in window.columns else []
        if len(unique_names) >= min_insiders:
            total_value = float(window["transaction_value"].sum()) if "transaction_value" in window.columns else 0.0
            clusters.append(ClusterEvent(
                start_date=start, end_date=end,
                n_insiders=int(len(unique_names)),
                total_value_usd=total_value,
                insider_names=list(map(str, unique_names))[:10],
            ))
            last_cluster_end = end
    return clusters


def _executive_activity(df: pd.DataFrame, *, keywords: tuple[str, ...],
                        role: str) -> Optional[ExecutiveActivity]:
    if df.empty or "typeOfOwner" not in df.columns:
        return None
    mask = df["typeOfOwner"].astype(str).str.lower().apply(
        lambda x: any(k in x for k in keywords)
    )
    sub = df[mask]
    if sub.empty:
        return None
    n_buys = int(sub.apply(_is_buy, axis=1).sum())
    n_sells = int(sub.apply(_is_sell, axis=1).sum())
    return ExecutiveActivity(
        role=role,
        n_transactions=int(len(sub)),
        n_buys=n_buys, n_sells=n_sells,
        net_value_usd=_net_value(sub),
    )


def _score(net_usd: float, clusters: list[ClusterEvent],
           ceo: Optional[ExecutiveActivity], trend: str) -> tuple[int, str, str]:
    score = 50
    if net_usd > 50_000_000:
        score += 25
    elif net_usd > 10_000_000:
        score += 15
    elif net_usd > 1_000_000:
        score += 7
    elif net_usd < -50_000_000:
        score -= 5      # heavy selling — but don't over-penalise (insiders have many reasons to sell)

    if len(clusters) >= 2:
        score += 15
    elif len(clusters) == 1:
        score += 8

    if ceo is not None and ceo.net_value_usd > 1_000_000:
        score += 15
    elif ceo is not None and ceo.net_value_usd > 100_000:
        score += 7

    if trend == "increasing":
        score += 5
    elif trend == "decreasing":
        score -= 3

    score = max(0, min(100, score))
    if score >= 75:
        return score, "green", "Strong insider conviction — significant buying with cluster activity."
    if score >= 60:
        return score, "green", "Positive insider sentiment — insiders accumulating."
    if score >= 40:
        return score, "yellow", "Mixed insider signals — monitor for changes."
    if score >= 25:
        return score, "yellow", "Weak insider sentiment — more selling than buying."
    return score, "red", "Negative insider sentiment — heavy selling."


# ============================================================
# Public API
# ============================================================
def analyze_insider_activity(ticker: str, *, months: int = 24) -> InsiderActivity:
    """Pull Form-4 data and roll it into an ``InsiderActivity`` summary."""
    try:
        from data import fmp_extras
    except Exception:
        return InsiderActivity(
            available=False, flag="unknown", score=0,
            note="fmp_extras module unavailable.",
        )

    if not fmp_extras.is_available():
        return InsiderActivity(
            available=False, flag="unknown", score=0,
            note=("FMP_API_KEY not configured. Insider analysis needs FMP "
                  "(yfinance does not expose Form-4 data reliably)."),
        )

    df = fmp_extras.fetch_insider_transactions(ticker, limit=200)
    if df.empty:
        return InsiderActivity(
            available=False, flag="unknown", score=0,
            note="No insider transactions returned by FMP for this ticker.",
        )

    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months)
    if "transactionDate" in df.columns:
        df = df[df["transactionDate"].fillna(cutoff - pd.Timedelta(days=1)) >= cutoff]
    if df.empty:
        return InsiderActivity(
            available=False, flag="unknown", score=0,
            note=f"No insider transactions in the last {months} months.",
        )

    purchases = df[df.apply(_is_buy, axis=1)]
    sales = df[df.apply(_is_sell, axis=1)]
    awards = df[df.apply(_is_award, axis=1)]

    total_bought = float(purchases["transaction_value"].sum()) if "transaction_value" in purchases.columns else 0.0
    total_sold = float(sales["transaction_value"].sum()) if "transaction_value" in sales.columns else 0.0
    net_activity = total_bought - total_sold

    # Recent 6m vs prior 6m
    today = pd.Timestamp.now()
    cut_recent = today - pd.DateOffset(months=6)
    cut_prior = today - pd.DateOffset(months=12)
    recent = df[df["transactionDate"] >= cut_recent] if "transactionDate" in df.columns else df.iloc[0:0]
    prior = df[(df["transactionDate"] >= cut_prior) & (df["transactionDate"] < cut_recent)] if "transactionDate" in df.columns else df.iloc[0:0]
    recent_net = _net_value(recent)
    prior_net = _net_value(prior)
    if abs(recent_net - prior_net) < 100_000:
        trend = "stable"
    elif recent_net > prior_net:
        trend = "increasing"
    else:
        trend = "decreasing"

    clusters = _detect_clusters(purchases)

    ceo = _executive_activity(
        df, keywords=("ceo", "chief executive", "president"), role="CEO",
    )
    cfo = _executive_activity(
        df, keywords=("cfo", "chief financial"), role="CFO",
    )

    score, flag, interp = _score(net_activity, clusters, ceo, trend)

    return InsiderActivity(
        available=True, flag=flag, score=score, interpretation=interp,
        n_transactions=len(df),
        n_purchases=len(purchases),
        n_sales=len(sales),
        n_awards=len(awards),
        total_bought_usd=total_bought,
        total_sold_usd=total_sold,
        net_activity_usd=net_activity,
        recent_6m_net_usd=recent_net,
        prior_6m_net_usd=prior_net,
        trend=trend,
        clusters=clusters,
        ceo=ceo, cfo=cfo,
        raw=df,
    )
