"""
Combine intrinsic-value estimates (DCF, comparables, MC, DDM, RI, EPV,
Multiples) into a single point estimate, a (low, high) range, an
inter-quartile range (p25, p75), and a confidence flag.

Each model contributes its per-share intrinsic value. Profile-specific
weights from :data:`PROFILE_WEIGHTS` decide how heavily to load each.
Models that failed (returned None) get their weight redistributed
across survivors. Models whose output is more than ``sanity_clip_threshold``
off the current market price are penalised (weight × 0.3) on the
assumption that they're misapplied to this business model rather than
revealing a real mispricing — the user-visible result is therefore
robust to a single broken model dragging the aggregate to absurd values.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.constants import RATING_THRESHOLDS


# ============================================================
# Profile → model weights
# ============================================================
PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "steady_compounder": {
        "dcf": 0.15, "epv": 0.40, "multiples": 0.35,
        "comps": 0.05, "ddm": 0.05, "ri": 0.0, "monte_carlo": 0.0,
    },
    "growth_tech": {
        "dcf": 0.30, "epv": 0.15, "multiples": 0.30,
        "comps": 0.10, "monte_carlo": 0.10, "ddm": 0.0, "ri": 0.05,
    },
    "cyclical": {
        "dcf": 0.10, "epv": 0.30, "multiples": 0.45,
        "comps": 0.10, "monte_carlo": 0.05, "ddm": 0.0, "ri": 0.0,
    },
    "bank": {
        "ri": 0.45, "ddm": 0.30, "multiples": 0.20, "comps": 0.05,
        "dcf": 0.0, "epv": 0.0, "monte_carlo": 0.0,
    },
    "insurance": {
        "ri": 0.45, "ddm": 0.30, "multiples": 0.20, "comps": 0.05,
        "dcf": 0.0, "epv": 0.0, "monte_carlo": 0.0,
    },
    "reit": {
        "ddm": 0.50, "multiples": 0.30, "comps": 0.15, "epv": 0.05,
        "dcf": 0.0, "monte_carlo": 0.0, "ri": 0.0,
    },
    "dividend_payer": {
        "ddm": 0.30, "epv": 0.25, "multiples": 0.25,
        "dcf": 0.10, "comps": 0.10, "monte_carlo": 0.0, "ri": 0.0,
    },
    "default": {
        "dcf": 0.20, "epv": 0.25, "multiples": 0.30,
        "comps": 0.10, "monte_carlo": 0.05, "ddm": 0.05, "ri": 0.05,
    },
}


# ============================================================
# Result dataclass
# ============================================================
@dataclass
class AggregatedValuation:
    intrinsic_per_share: float
    range_low: float                              # back-compat: cv-scaled band
    range_high: float
    range_p25: float                              # NEW: inter-quartile across surviving models
    range_p75: float
    weights_used: dict[str, float]
    contributions: dict[str, float]               # value × weight per model
    raw_estimates: dict[str, float] = field(default_factory=dict)
    clipped_models: list[str] = field(default_factory=list)
    dispersion_cv: float = 0.0                    # coefficient of variation
    confidence: str = "high"                      # high | medium | low
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
    epv: Optional[float] = None,
    multiples: Optional[float] = None,
    profile: Optional[str] = None,
    current_price: Optional[float] = None,
    sector: Optional[str] = None,               # kept for back-compat; ignored when profile set
    range_band: float = 0.20,
    sanity_clip_threshold: float = 0.60,
) -> AggregatedValuation:
    """Combine the per-share intrinsic values into one aggregated result.

    Args:
      profile: One of the keys in :data:`PROFILE_WEIGHTS`. Falls back to
               "default" when None or unknown. Replaces the old sector
               argument (still accepted but unused — callers should
               migrate to passing profile explicitly).
      current_price: Used for sanity-clipping wildly off models. When
               omitted, no clipping is applied (back-compat path).
      sanity_clip_threshold: Fractional gap above which a model's
               weight is reduced 70% (e.g. 0.60 ⇒ a model whose output
               is <40% or >160% of the current price is penalised).
    """
    profile_key = profile if (profile and profile in PROFILE_WEIGHTS) else "default"
    base_weights = PROFILE_WEIGHTS[profile_key]

    raw = {
        "dcf": dcf, "comps": comparables, "monte_carlo": monte_carlo,
        "ddm": ddm, "ri": residual_income,
        "epv": epv, "multiples": multiples,
    }
    survivors = {k: float(v) for k, v in raw.items()
                 if v is not None and np.isfinite(v) and v > 0}
    # raw_estimates surfaces everything that came in finite + positive so
    # the UI can render the per-model breakdown including clipped ones.
    raw_estimates = dict(survivors)

    if not survivors:
        return AggregatedValuation(
            intrinsic_per_share=float("nan"),
            range_low=float("nan"), range_high=float("nan"),
            range_p25=float("nan"), range_p75=float("nan"),
            weights_used={}, contributions={}, raw_estimates={},
            clipped_models=[],
            confidence="low", profile=profile_key, n_models_used=0,
        )

    # ---- Sanity clip ----
    clipped_set: set[str] = set()
    if current_price is not None and np.isfinite(current_price) and current_price > 0:
        lo_bound = current_price * (1.0 - sanity_clip_threshold)
        hi_bound = current_price * (1.0 + sanity_clip_threshold)
        for k, v in survivors.items():
            if v < lo_bound or v > hi_bound:
                clipped_set.add(k)
        sane = {k: v for k, v in survivors.items() if k not in clipped_set}
        # Fallback: if clipping leaves <2 sane models, include the clipped
        # ones too but they'll be penalised in the weight stage.
        if len(sane) < 2:
            sane = dict(survivors)
        usable = sane
    else:
        usable = dict(survivors)

    # ---- Weights ----
    raw_w = {k: base_weights.get(k, 0.0) for k in usable}
    # Penalise clipped models that still made it into the usable set
    # (only happens in the <2 sane fallback).
    for k in list(raw_w):
        if k in clipped_set:
            raw_w[k] *= 0.3
    total = sum(raw_w.values())
    if total <= 0:
        raw_w = {k: 1.0 for k in usable}
        total = float(len(usable))
    weights = {k: raw_w[k] / total for k in usable}

    contribs = {k: weights[k] * usable[k] for k in usable}
    intrinsic = float(sum(contribs.values()))

    # ---- Inter-quartile range across surviving models ----
    if len(usable) >= 2:
        values = np.array(list(usable.values()), dtype=float)
        range_p25 = float(np.percentile(values, 25))
        range_p75 = float(np.percentile(values, 75))
    else:
        range_p25 = intrinsic * 0.85
        range_p75 = intrinsic * 1.15

    # ---- CV-scaled band (back-compat range_low / range_high) ----
    cv_values = np.array(list(usable.values()), dtype=float)
    cv = float(cv_values.std(ddof=0) / cv_values.mean()) if cv_values.mean() > 0 else 0.0

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
        range_p25=float(range_p25),
        range_p75=float(range_p75),
        weights_used=weights,
        contributions=contribs,
        raw_estimates=raw_estimates,
        clipped_models=sorted(clipped_set),
        dispersion_cv=float(cv),
        confidence=confidence,
        profile=profile_key,
        n_models_used=len(usable),
    )
