"""
Trading multiples comparable valuation.

Peer multiples (P/E, EV/EBITDA, P/S, P/B) are aggregated to a robust
median after outlier filtering (IQR fences or symmetric winsorization,
selectable via ``COMPARABLES_FILTERING['method']``). Each multiple is
then applied to the target company's corresponding fundamental to back
out an implied equity value per share.

Inputs are intentionally lightweight — a list of ``PeerSnapshot`` rows
that any data provider can produce. The model never raises on a single
bad peer; it filters or omits.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from core.constants import COMPARABLES_FILTERING
from core.exceptions import InsufficientDataError, ValuationError


# ============================================================
# Inputs / outputs
# ============================================================
@dataclass
class PeerSnapshot:
    """A single peer's trailing multiples + the data needed to recompute."""
    ticker: str
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    net_income: Optional[float] = None
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    book_value: Optional[float] = None        # total stockholders equity
    price: Optional[float] = None
    eps: Optional[float] = None

    # Pre-computed multiples (preferred when available — avoids divide-by-zero
    # surprises when a peer has near-zero EBITDA, etc.)
    pe: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ps: Optional[float] = None
    pb: Optional[float] = None
    revenue_yoy: Optional[float] = None  # YoY revenue growth in % (e.g. 12.5 for +12.5%)


@dataclass
class TargetFundamentals:
    """The company being valued — supplies the denominators."""
    net_income: Optional[float] = None
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    book_value: Optional[float] = None
    shares_outstanding: Optional[float] = None
    cash: float = 0.0
    debt: float = 0.0


@dataclass
class MultipleResult:
    """One multiple's filtered distribution + implied per-share value."""
    name: str                          # "P/E", "EV/EBITDA", ...
    raw_values: list[float]
    filtered_values: list[float]
    median: float
    p25: float
    p75: float
    implied_per_share: Optional[float]
    n_peers_after_filter: int


@dataclass
class ComparablesResult:
    """Aggregate output across all multiples."""
    multiples: dict[str, MultipleResult] = field(default_factory=dict)
    implied_per_share_median: Optional[float] = None
    implied_per_share_low: Optional[float] = None       # 25th percentile
    implied_per_share_high: Optional[float] = None      # 75th percentile
    method: str = "iqr"
    n_peers_input: int = 0


# ============================================================
# Filtering
# ============================================================
def _iqr_filter(values: list[float], multiplier: float) -> list[float]:
    """Drop points outside [Q1 - k·IQR, Q3 + k·IQR]."""
    if len(values) < 4:
        return values
    arr = np.asarray(values, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - multiplier * iqr, q3 + multiplier * iqr
    return [float(v) for v in arr if lo <= v <= hi]


def _winsorize(values: list[float], lower: float, upper: float) -> list[float]:
    """Clip to the [lower, upper] quantile band."""
    if len(values) < 4:
        return values
    arr = np.asarray(values, dtype=float)
    lo, hi = np.quantile(arr, [lower, upper])
    return [float(np.clip(v, lo, hi)) for v in arr]


def _filter(values: list[float], cfg: dict) -> list[float]:
    method = cfg.get("method", "iqr")
    cleaned = [float(v) for v in values
               if v is not None and np.isfinite(v) and v > 0]
    if method == "winsorize":
        return _winsorize(cleaned, cfg["winsorize_lower"], cfg["winsorize_upper"])
    return _iqr_filter(cleaned, cfg["iqr_multiplier"])


# ============================================================
# Multiple extraction
# ============================================================
def _peer_multiple(peer: PeerSnapshot, kind: str) -> Optional[float]:
    """Return a single peer's multiple, computing from raw fields if needed."""
    if kind == "pe":
        if peer.pe is not None:
            return peer.pe
        if peer.market_cap and peer.net_income and peer.net_income > 0:
            return peer.market_cap / peer.net_income
        if peer.price and peer.eps and peer.eps > 0:
            return peer.price / peer.eps
    elif kind == "ev_ebitda":
        if peer.ev_ebitda is not None:
            return peer.ev_ebitda
        if peer.enterprise_value and peer.ebitda and peer.ebitda > 0:
            return peer.enterprise_value / peer.ebitda
    elif kind == "ps":
        if peer.ps is not None:
            return peer.ps
        if peer.market_cap and peer.revenue and peer.revenue > 0:
            return peer.market_cap / peer.revenue
    elif kind == "pb":
        if peer.pb is not None:
            return peer.pb
        if peer.market_cap and peer.book_value and peer.book_value > 0:
            return peer.market_cap / peer.book_value
    return None


def _build_multiple(
    name: str,
    kind: str,
    peers: list[PeerSnapshot],
    target: TargetFundamentals,
    cfg: dict,
) -> Optional[MultipleResult]:
    """Compute a single MultipleResult, returns None if too few peers."""
    raw = [_peer_multiple(p, kind) for p in peers]
    raw_clean = [v for v in raw if v is not None]
    if not raw_clean:
        return None

    filtered = _filter(raw_clean, cfg)
    if len(filtered) < cfg.get("min_peers_after_filter", 3):
        return None

    arr = np.asarray(filtered, dtype=float)
    median = float(np.median(arr))
    p25 = float(np.percentile(arr, 25))
    p75 = float(np.percentile(arr, 75))

    implied = _apply_multiple(name, median, target)

    return MultipleResult(
        name=name,
        raw_values=[float(v) for v in raw_clean],
        filtered_values=[float(v) for v in filtered],
        median=median,
        p25=p25,
        p75=p75,
        implied_per_share=implied,
        n_peers_after_filter=len(filtered),
    )


def _apply_multiple(
    name: str, multiple: float, t: TargetFundamentals
) -> Optional[float]:
    """Convert a peer-median multiple into an implied per-share value."""
    if not t.shares_outstanding or t.shares_outstanding <= 0:
        return None

    if name == "P/E":
        if t.net_income is None or t.net_income <= 0:
            return None
        equity_value = multiple * t.net_income
    elif name == "EV/EBITDA":
        if t.ebitda is None or t.ebitda <= 0:
            return None
        ev = multiple * t.ebitda
        equity_value = ev + t.cash - t.debt
    elif name == "P/S":
        if t.revenue is None or t.revenue <= 0:
            return None
        equity_value = multiple * t.revenue
    elif name == "P/B":
        if t.book_value is None or t.book_value <= 0:
            return None
        equity_value = multiple * t.book_value
    else:
        return None

    if equity_value <= 0:
        return None
    return float(equity_value / t.shares_outstanding)


# ============================================================
# Public API
# ============================================================
def value_by_comparables(
    *,
    peers: Iterable[PeerSnapshot],
    target: TargetFundamentals,
    multiples: tuple[str, ...] = ("P/E", "EV/EBITDA", "P/S", "P/B"),
    config: Optional[dict] = None,
) -> ComparablesResult:
    """
    Run the full comparables valuation across all requested multiples.

    Aggregates the per-multiple implied values into a single (low, mid,
    high) range using the 25/50/75 percentiles across multiples that
    produced a value.
    """
    cfg = {**COMPARABLES_FILTERING, **(config or {})}
    peers_list = list(peers)
    if not peers_list:
        raise InsufficientDataError("No peers provided for comparables valuation")

    kinds = {"P/E": "pe", "EV/EBITDA": "ev_ebitda", "P/S": "ps", "P/B": "pb"}
    out = ComparablesResult(method=cfg.get("method", "iqr"), n_peers_input=len(peers_list))

    for name in multiples:
        kind = kinds.get(name)
        if kind is None:
            continue
        m = _build_multiple(name, kind, peers_list, target, cfg)
        if m is not None:
            out.multiples[name] = m

    implieds = [m.implied_per_share for m in out.multiples.values()
                if m.implied_per_share is not None]
    if implieds:
        arr = np.asarray(implieds, dtype=float)
        out.implied_per_share_median = float(np.median(arr))
        if len(arr) >= 2:
            out.implied_per_share_low = float(np.percentile(arr, 25))
            out.implied_per_share_high = float(np.percentile(arr, 75))
        else:
            out.implied_per_share_low = out.implied_per_share_median
            out.implied_per_share_high = out.implied_per_share_median

    return out


def comparables_table(result: ComparablesResult) -> pd.DataFrame:
    """Pretty per-multiple summary suitable for st.dataframe."""
    rows = []
    for name, m in result.multiples.items():
        rows.append({
            "Multiple": name,
            "Peers (filtered)": m.n_peers_after_filter,
            "Median": m.median,
            "P25": m.p25,
            "P75": m.p75,
            "Implied $/share": m.implied_per_share,
        })
    return pd.DataFrame(rows)
