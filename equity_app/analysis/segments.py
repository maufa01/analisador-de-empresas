"""
Revenue segmentation — by product line and by region — plus a
sum-of-the-parts (SOTP) valuation built from segment revenue × default
sector multiples.

Source: ``data.fmp_extras.fetch_revenue_by_segment`` /
``fetch_revenue_by_geography``. Both return empty DataFrames without
``FMP_API_KEY`` set, so the result dataclass exposes ``available=False``
in that case.

SOTP is intentionally simple: revenue × an EV/Sales multiple keyed off
keywords in the segment name (services / hardware / cloud / …). It's
useful as a sanity check, not as a primary valuation. Treat it as
directional.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ============================================================
# Result types
# ============================================================
@dataclass
class SegmentMetric:
    name: str
    current_revenue: float
    share_of_revenue_pct: float
    yoy_change_pct: Optional[float] = None
    cagr_5y_pct: Optional[float] = None


@dataclass
class SegmentsResult:
    available: bool
    n_segments: int = 0
    total_revenue: float = 0.0
    segments: list[SegmentMetric] = field(default_factory=list)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    note: str = ""


@dataclass
class GeographyResult:
    available: bool
    n_regions: int = 0
    total_revenue: float = 0.0
    regions: list[SegmentMetric] = field(default_factory=list)
    domestic_pct: Optional[float] = None
    international_pct: Optional[float] = None
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    note: str = ""


@dataclass
class SOTPSegment:
    name: str
    revenue: float
    multiple: float
    method: str
    implied_ev: float
    share_of_value_pct: float


@dataclass
class SOTPResult:
    available: bool
    total_ev: Optional[float] = None
    net_debt: Optional[float] = None
    implied_market_cap: Optional[float] = None
    implied_per_share: Optional[float] = None
    current_price: Optional[float] = None
    premium_to_sotp_pct: Optional[float] = None
    breakdown: list[SOTPSegment] = field(default_factory=list)
    note: str = ""


# ============================================================
# Helpers
# ============================================================
def _build_segment_metrics(history: pd.DataFrame) -> list[SegmentMetric]:
    if history is None or history.empty:
        return []
    latest = history.iloc[-1]
    prior = history.iloc[-2] if len(history) >= 2 else None
    five_back = history.iloc[-5] if len(history) >= 5 else None
    total = float(latest.dropna().sum())
    if total <= 0:
        return []

    metrics: list[SegmentMetric] = []
    for col in history.columns:
        cur = latest.get(col)
        if pd.isna(cur) or cur == 0:
            continue
        cur = float(cur)
        share = cur / total * 100

        yoy = None
        if prior is not None and pd.notna(prior.get(col)) and prior.get(col) != 0:
            yoy = (cur / float(prior[col]) - 1) * 100

        cagr = None
        if five_back is not None and pd.notna(five_back.get(col)) and five_back.get(col) > 0:
            cagr = ((cur / float(five_back[col])) ** (1 / 4) - 1) * 100

        metrics.append(SegmentMetric(
            name=str(col),
            current_revenue=cur,
            share_of_revenue_pct=share,
            yoy_change_pct=yoy,
            cagr_5y_pct=cagr,
        ))
    metrics.sort(key=lambda m: m.current_revenue, reverse=True)
    return metrics


# ============================================================
# Public API — segments / geography
# ============================================================
def analyze_segments(ticker: str) -> SegmentsResult:
    try:
        from data import fmp_extras
    except Exception:
        return SegmentsResult(available=False, note="fmp_extras unavailable")

    if not fmp_extras.is_available():
        return SegmentsResult(
            available=False,
            note=("FMP_API_KEY not configured. Segment data is FMP-only "
                  "(yfinance does not expose product-line revenue)."),
        )

    history = fmp_extras.fetch_revenue_by_segment(ticker)
    if history.empty:
        return SegmentsResult(available=False,
                              note="No segment data returned by FMP for this ticker.")

    metrics = _build_segment_metrics(history)
    total = sum(m.current_revenue for m in metrics)
    return SegmentsResult(
        available=True,
        n_segments=len(metrics),
        total_revenue=total,
        segments=metrics,
        history=history,
    )


def analyze_geography(ticker: str) -> GeographyResult:
    try:
        from data import fmp_extras
    except Exception:
        return GeographyResult(available=False, note="fmp_extras unavailable")

    if not fmp_extras.is_available():
        return GeographyResult(
            available=False,
            note=("FMP_API_KEY not configured. Geographic revenue is "
                  "FMP-only."),
        )

    history = fmp_extras.fetch_revenue_by_geography(ticker)
    if history.empty:
        return GeographyResult(available=False,
                               note="No geographic data returned by FMP.")

    metrics = _build_segment_metrics(history)
    total = sum(m.current_revenue for m in metrics)

    # Crude "domestic" detector — accounts for FMP's wildly inconsistent
    # naming across companies ("Americas", "United States", "U.S.", etc.)
    domestic_keys = {"united states", "americas", "usa", "u.s.", "us",
                     "north america", "domestic"}
    dom_revenue = sum(
        m.current_revenue for m in metrics
        if any(k in m.name.lower() for k in domestic_keys)
    )
    dom_pct = (dom_revenue / total * 100) if total > 0 else None
    intl_pct = (100 - dom_pct) if dom_pct is not None else None

    return GeographyResult(
        available=True,
        n_regions=len(metrics),
        total_revenue=total,
        regions=metrics,
        domestic_pct=dom_pct,
        international_pct=intl_pct,
        history=history,
    )


# ============================================================
# SOTP valuation
# ============================================================
def _default_segment_multiple(segment_name: str) -> tuple[float, str]:
    """Heuristic EV/Sales multiple by segment-name keywords."""
    s = segment_name.lower()
    if any(k in s for k in ("service", "subscription", "saas", "cloud", "software")):
        return 10.0, "EV/Sales (services premium)"
    if any(k in s for k in ("ai", "data", "advertising", "ads")):
        return 8.0, "EV/Sales (growth)"
    if any(k in s for k in ("hardware", "iphone", "mac", "ipad", "device", "product", "equipment")):
        return 3.5, "EV/Sales (hardware)"
    if any(k in s for k in ("retail", "store", "consumer")):
        return 2.5, "EV/Sales (retail)"
    return 5.0, "EV/Sales (default)"


def value_segments_sotp(
    *, segments: SegmentsResult,
    market_cap: Optional[float] = None,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    current_price: Optional[float] = None,
    multiples_override: Optional[dict[str, tuple[float, str]]] = None,
) -> SOTPResult:
    if not segments.available or not segments.segments:
        return SOTPResult(available=False,
                          note="Segments data required for SOTP.")

    breakdown: list[SOTPSegment] = []
    total_ev = 0.0
    for seg in segments.segments:
        if multiples_override and seg.name in multiples_override:
            mult, method = multiples_override[seg.name]
        else:
            mult, method = _default_segment_multiple(seg.name)
        ev = seg.current_revenue * mult
        breakdown.append(SOTPSegment(
            name=seg.name, revenue=seg.current_revenue,
            multiple=mult, method=method, implied_ev=ev,
            share_of_value_pct=0.0,    # filled in after the loop
        ))
        total_ev += ev

    if total_ev > 0:
        for b in breakdown:
            b.share_of_value_pct = b.implied_ev / total_ev * 100

    implied_mcap = None
    implied_per_share = None
    premium = None
    if market_cap is not None and net_debt is not None:
        implied_mcap = total_ev - net_debt
    if (shares_outstanding and shares_outstanding > 0
            and implied_mcap is not None):
        implied_per_share = implied_mcap / shares_outstanding
    if (current_price and current_price > 0 and implied_per_share
            and implied_per_share > 0):
        premium = (current_price / implied_per_share - 1) * 100

    return SOTPResult(
        available=True,
        total_ev=total_ev,
        net_debt=net_debt,
        implied_market_cap=implied_mcap,
        implied_per_share=implied_per_share,
        current_price=current_price,
        premium_to_sotp_pct=premium,
        breakdown=breakdown,
        note=("Default multiples are heuristic by segment-name keyword. "
              "Override per-segment for institutional rigor."),
    )
