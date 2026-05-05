"""
Combine the five intrinsic-value estimates (DCF, comparables, MC,
DDM, RI) into a single point estimate plus a (low, high) range and a
confidence flag.

Each model contributes its per-share intrinsic value; sector-specific
weights from ``SECTOR_VALUATION_WEIGHTS`` decide how heavily to load
each. Models that failed (returned None) get their weight redistributed
proportionally across the survivors.

Confidence is derived from the coefficient of variation across the
contributing models — if the dispersion is wide, the rating engine
should temper its conviction.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.constants import (
    RATING_THRESHOLDS, SECTOR_VALUATION_WEIGHTS,
)


# ============================================================
# Sector → weight-key mapping
# ============================================================
SECTOR_PROFILE: dict[str, str] = {
    "Technology":             "tech_growth",
    "Communication Services": "tech_growth",
    "Consumer Cyclical":      "default",
    "Consumer Defensive":     "mature_div",
    "Healthcare":             "default",
    "Industrials":            "default",
    "Energy":                 "default",
    "Utilities":              "mature_div",
    "Basic Materials":        "default",
    "Real Estate":            "mature_div",
    "Financial Services":     "financials",
}


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class AggregatedValuation:
    intrinsic_per_share: float
    range_low: float
    range_high: float
    weights_used: dict[str, float]
    contributions: dict[str, float]              # value × weight per model
    raw_estimates: dict[str, float] = field(default_factory=dict)
    dispersion_cv: float = 0.0                   # coefficient of variation
    confidence: str = "high"                     # high | medium | low
    profile: str = "default"
    n_models_used: int = 0


# ============================================================
# Public API
# ============================================================
def aggregate(
    *,
    dcf: Optional[float] = None,
    comparables: Optional[float] = None,
    monte_carlo: Optional[float] = None,
    ddm: Optional[float] = None,
    residual_income: Optional[float] = None,
    sector: Optional[str] = None,
    range_band: float = 0.20,
) -> AggregatedValuation:
    """
    Combine the per-share intrinsic values from the 5 models.

    ``range_band`` widens the (low, high) band as a fraction of the
    weighted point estimate. Defaults to 20% — i.e. the band is the
    intrinsic ± 20% scaled by the dispersion CV (clipped at 50%).
    """
    profile_key = SECTOR_PROFILE.get(sector or "", "default") if sector else "default"
    base_weights = SECTOR_VALUATION_WEIGHTS.get(profile_key,
                                                SECTOR_VALUATION_WEIGHTS["default"])

    raw = {
        "dcf": dcf, "comps": comparables, "monte_carlo": monte_carlo,
        "ddm": ddm, "ri": residual_income,
    }
    survivors = {k: float(v) for k, v in raw.items()
                 if v is not None and np.isfinite(v) and v > 0}

    if not survivors:
        return AggregatedValuation(
            intrinsic_per_share=float("nan"),
            range_low=float("nan"), range_high=float("nan"),
            weights_used={}, contributions={}, raw_estimates={},
            confidence="low", profile=profile_key, n_models_used=0,
        )

    raw_w = {k: base_weights.get(k, 0.0) for k in survivors}
    total = sum(raw_w.values())
    if total <= 0:
        # Sector profile zeroes every survivor — fall back to equal weights
        raw_w = {k: 1.0 for k in survivors}
        total = float(len(survivors))
    weights = {k: raw_w[k] / total for k in survivors}

    contribs = {k: weights[k] * survivors[k] for k in survivors}
    intrinsic = float(sum(contribs.values()))

    values = np.array(list(survivors.values()), dtype=float)
    cv = float(values.std(ddof=0) / values.mean()) if values.mean() > 0 else 0.0

    threshold = float(RATING_THRESHOLDS["low_confidence_dispersion"])
    if cv >= threshold:
        confidence = "low"
    elif cv >= threshold / 2:
        confidence = "medium"
    else:
        confidence = "high"

    band = float(np.clip(range_band * (1.0 + cv), 0.05, 0.50))
    low = intrinsic * (1.0 - band)
    high = intrinsic * (1.0 + band)

    return AggregatedValuation(
        intrinsic_per_share=intrinsic,
        range_low=float(low),
        range_high=float(high),
        weights_used=weights,
        contributions=contribs,
        raw_estimates=survivors,
        dispersion_cv=float(cv),
        confidence=confidence,
        profile=profile_key,
        n_models_used=len(survivors),
    )
