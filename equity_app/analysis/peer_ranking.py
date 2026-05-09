"""
Peer-relative ranking — percentile within the peer group on a curated
list of metrics across 5 categories: growth, profitability, efficiency,
solvency, valuation.

Operates on the same ``PeerSnapshot`` objects that drive comparables
valuation, augmented with target-only metrics computed from the
income/balance/cash DataFrames (revenue YoY, FCF margin etc.).

Returns a single dataclass per metric carrying:
  - the target's value
  - the peer-group percentile (0-100)
  - a categorical band (top decile / quartile / median / etc.)
  - a flag (✓ good / ⚠ neutral / ✗ poor) derived from the band
    AND the metric's "higher is better" semantics.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import math
import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow, cagr
from valuation.comparables import PeerSnapshot, _peer_multiple


# ============================================================
# Data classes
# ============================================================
@dataclass
class MetricRanking:
    metric:        str
    label:         str
    category:      str
    higher_better: bool
    target_value:  Optional[float]
    percentile:    Optional[float]                 # 0-100, None when uncomputable
    rank:          Optional[int]                   # 1 = best
    n_peers:       int
    band:          str                             # e.g. "top decile"
    flag:          str                             # "✓" / "⚠" / "✗"
    target_only_reason: str = ""                   # shown by the table for target-only rows


@dataclass
class PeerRankingResult:
    target_ticker:  str
    n_peers:        int
    by_category:    dict[str, list[MetricRanking]] = field(default_factory=dict)
    avg_percentile: dict[str, Optional[float]] = field(default_factory=dict)


# ============================================================
# Helpers — extracting metric values per snapshot / target
# ============================================================
def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _pe(p: PeerSnapshot) -> Optional[float]:
    return _safe(_peer_multiple(p, "pe"))


def _ev_ebitda(p: PeerSnapshot) -> Optional[float]:
    return _safe(_peer_multiple(p, "ev_ebitda"))


def _ps(p: PeerSnapshot) -> Optional[float]:
    return _safe(_peer_multiple(p, "ps"))


def _pb(p: PeerSnapshot) -> Optional[float]:
    return _safe(_peer_multiple(p, "pb"))


def _net_margin(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.revenue or p.revenue <= 0:
        return None
    return p.net_income / p.revenue * 100.0


def _operating_margin(p: PeerSnapshot) -> Optional[float]:
    # We don't ship operating income in the snapshot — fall back to
    # EBITDA margin as the closest proxy when ebitda is set.
    if p.ebitda is None or not p.revenue or p.revenue <= 0:
        return None
    return p.ebitda / p.revenue * 100.0


def _roe(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.book_value or p.book_value <= 0:
        return None
    return p.net_income / p.book_value * 100.0


# ---- Target-only metrics (need full DataFrames) ----
def _revenue_growth_1y(income: pd.DataFrame) -> Optional[float]:
    """1y revenue growth in %. Same shape as PeerSnapshot.revenue_yoy so
    targets and peers can be compared apples-to-apples."""
    rev = _get(income, "revenue")
    if rev is None:
        return None
    s = rev.dropna()
    if len(s) < 2 or s.iloc[-2] <= 0:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-2]) - 1.0) * 100.0


def _revenue_yoy_peer(p: PeerSnapshot) -> Optional[float]:
    return _safe(p.revenue_yoy)


def _fcf_growth_5y(cash: pd.DataFrame) -> Optional[float]:
    fcf = free_cash_flow(cash)
    if fcf is None:
        return None
    s = fcf.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    g = cagr(s, periods=min(5, len(s) - 1))
    return float(g) * 100.0 if math.isfinite(g) else None


def _eps_growth_5y(income: pd.DataFrame) -> Optional[float]:
    eps = _get(income, "eps")
    if eps is None:
        return None
    s = eps.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    g = cagr(s, periods=min(5, len(s) - 1))
    return float(g) * 100.0 if math.isfinite(g) else None


def _fcf_margin(income: pd.DataFrame, cash: pd.DataFrame) -> Optional[float]:
    rev = _get(income, "revenue")
    fcf = free_cash_flow(cash)
    if rev is None or fcf is None:
        return None
    rev_last = float(rev.dropna().iloc[-1]) if not rev.dropna().empty else None
    fcf_last = float(fcf.dropna().iloc[-1]) if not fcf.dropna().empty else None
    if rev_last is None or fcf_last is None or rev_last <= 0:
        return None
    return fcf_last / rev_last * 100.0


def _debt_to_equity(p: PeerSnapshot) -> Optional[float]:
    # Snapshot doesn't ship debt directly; approximate from market cap +
    # enterprise value when both present (EV − Mcap ≈ net debt, but we
    # accept the rough proxy here).
    if p.enterprise_value and p.market_cap and p.book_value and p.book_value > 0:
        proxy_debt = max(p.enterprise_value - p.market_cap, 0.0)
        return proxy_debt / p.book_value
    return None


def _earnings_yield(p: PeerSnapshot) -> Optional[float]:
    pe = _pe(p)
    return (1.0 / pe) * 100.0 if (pe and pe > 0) else None


# ============================================================
# Percentile + band classification
# ============================================================
def _percentile_rank(target_value: Optional[float],
                     peer_values: list[float],
                     *,
                     higher_better: bool) -> Optional[float]:
    if target_value is None:
        return None
    cleaned = [v for v in peer_values if v is not None and math.isfinite(v)]
    if not cleaned:
        return None
    universe = cleaned + [target_value]
    universe.sort(reverse=higher_better)
    rank = universe.index(target_value)              # 0 = best
    return (1.0 - rank / max(len(universe) - 1, 1)) * 100.0


def _band_and_flag(percentile: Optional[float], *, higher_better: bool) -> tuple[str, str]:
    """
    The percentile coming out of ``_percentile_rank`` is already
    normalised to 100 = best (lowest P/E for lower-better metrics,
    highest ROE for higher-better metrics) — no further inversion here.
    """
    if percentile is None:
        return "—", "—"
    if percentile >= 90:
        return "top decile", "✓"
    if percentile >= 75:
        return "top quartile", "✓"
    if percentile >= 50:
        return "above median", "⚠"
    if percentile >= 25:
        return "below median", "⚠"
    if percentile >= 10:
        return "bottom quartile", "✗"
    return "bottom decile", "✗"


# ============================================================
# Public API
# ============================================================
_METRIC_DEFS: list[dict] = [
    # ---- Growth ----
    {"metric": "revenue_growth_1y", "label": "Revenue growth 1y",
     "category": "Growth", "higher_better": True},
    {"metric": "fcf_growth_5y", "label": "FCF growth 5y",
     "category": "Growth", "higher_better": True, "target_only": True,
     "target_only_reason": "Requires multi-year FCF per peer (not in snapshot)"},
    {"metric": "eps_growth_5y", "label": "EPS growth 5y",
     "category": "Growth", "higher_better": True, "target_only": True,
     "target_only_reason": "Requires multi-year EPS per peer (not in snapshot)"},

    # ---- Profitability ----
    {"metric": "operating_margin", "label": "Operating margin",
     "category": "Profitability", "higher_better": True},
    {"metric": "net_margin", "label": "Net margin",
     "category": "Profitability", "higher_better": True},
    {"metric": "roe", "label": "ROE",
     "category": "Profitability", "higher_better": True},
    {"metric": "fcf_margin", "label": "FCF margin",
     "category": "Profitability", "higher_better": True, "target_only": True,
     "target_only_reason": "Requires FCF per peer (not in snapshot)"},

    # ---- Solvency ----
    {"metric": "debt_to_equity", "label": "Debt / Equity",
     "category": "Solvency", "higher_better": False},

    # ---- Valuation ----
    {"metric": "pe", "label": "P/E",
     "category": "Valuation", "higher_better": False},
    {"metric": "ev_ebitda", "label": "EV/EBITDA",
     "category": "Valuation", "higher_better": False},
    {"metric": "ps", "label": "P/S",
     "category": "Valuation", "higher_better": False},
    {"metric": "pb", "label": "P/B",
     "category": "Valuation", "higher_better": False},
    {"metric": "earnings_yield", "label": "Earnings yield",
     "category": "Valuation", "higher_better": True},
]


def _value_for(p: PeerSnapshot, metric: str) -> Optional[float]:
    """Map a snapshot + metric key → numeric value."""
    return {
        "revenue_growth_1y": _revenue_yoy_peer,
        "operating_margin": _operating_margin,
        "net_margin":       _net_margin,
        "roe":              _roe,
        "debt_to_equity":   _debt_to_equity,
        "pe":               _pe,
        "ev_ebitda":        _ev_ebitda,
        "ps":               _ps,
        "pb":               _pb,
        "earnings_yield":   _earnings_yield,
    }.get(metric, lambda _p: None)(p)


def compute_peer_rankings(
    *,
    target_ticker: str,
    target_income: pd.DataFrame,
    target_balance: pd.DataFrame,
    target_cash: pd.DataFrame,
    target_market_cap: Optional[float],
    target_enterprise_value: Optional[float],
    peers: list[PeerSnapshot],
) -> PeerRankingResult:
    """Build the full per-category ranking for the target vs the peer group."""
    n = len(peers)

    # Compute the target-only values once
    target_only_values: dict[str, Optional[float]] = {
        "fcf_growth_5y": _fcf_growth_5y(target_cash),
        "eps_growth_5y": _eps_growth_5y(target_income),
        "fcf_margin":    _fcf_margin(target_income, target_cash),
    }

    # Synthetic snapshot for snapshot-style metrics
    last_inc = target_income.iloc[-1] if not target_income.empty else None
    last_bal = target_balance.iloc[-1] if not target_balance.empty else None

    def _pick(row, *keys):
        if row is None:
            return None
        for k in keys:
            if k in row and pd.notna(row[k]):
                return float(row[k])
        return None

    target_snap = PeerSnapshot(
        ticker=target_ticker,
        market_cap=target_market_cap,
        enterprise_value=target_enterprise_value,
        net_income=_pick(last_inc, "netIncome"),
        revenue=_pick(last_inc, "revenue"),
        # SEC EDGAR doesn't ship ebitda — fall back to operatingIncome so
        # _operating_margin still produces a value (it underestimates by
        # D&A but that's <5% of revenue for most names).
        ebitda=_pick(last_inc, "ebitda", "operatingIncome"),
        book_value=_pick(last_bal, "totalStockholdersEquity", "totalEquity"),
        revenue_yoy=_revenue_growth_1y(target_income),
    )

    by_category: dict[str, list[MetricRanking]] = {}
    pct_buckets: dict[str, list[float]] = {}

    for spec in _METRIC_DEFS:
        metric = spec["metric"]
        higher_better = spec["higher_better"]
        target_only = spec.get("target_only", False)

        if target_only:
            target_val = target_only_values.get(metric)
            peer_vals: list[Optional[float]] = []         # no peer values for these
        else:
            target_val = _value_for(target_snap, metric)
            peer_vals = [_value_for(p, metric) for p in peers]

        peer_vals_clean = [v for v in peer_vals if v is not None]
        if target_only or not peer_vals_clean:
            percentile = None
            rank = None
        else:
            percentile = _percentile_rank(
                target_val, peer_vals_clean, higher_better=higher_better,
            )
            if percentile is not None:
                # Ranking position (1-indexed)
                ordered = sorted(peer_vals_clean + [target_val],
                                 reverse=higher_better)
                try:
                    rank = ordered.index(target_val) + 1
                except ValueError:
                    rank = None
            else:
                rank = None

        band, flag = _band_and_flag(percentile, higher_better=higher_better)
        ranking = MetricRanking(
            metric=metric, label=spec["label"], category=spec["category"],
            higher_better=higher_better, target_value=target_val,
            percentile=percentile, rank=rank,
            n_peers=len(peer_vals_clean),
            band=band, flag=flag,
            target_only_reason=spec.get("target_only_reason", ""),
        )
        by_category.setdefault(spec["category"], []).append(ranking)
        if percentile is not None:
            pct_buckets.setdefault(spec["category"], []).append(percentile)

    avg_percentile = {
        cat: (sum(vals) / len(vals)) if vals else None
        for cat, vals in pct_buckets.items()
    }
    # Categories that had no measurable percentiles still appear so the
    # UI can show a "—"
    for cat in by_category:
        avg_percentile.setdefault(cat, None)

    return PeerRankingResult(
        target_ticker=target_ticker,
        n_peers=n,
        by_category=by_category,
        avg_percentile=avg_percentile,
    )
