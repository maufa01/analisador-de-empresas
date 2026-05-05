"""
Final analyst rating — combines composite score, upside vs aggregator,
and dispersion confidence into one of:

    STRONG BUY · BUY · HOLD · SELL · STRONG SELL

Logic (in order):
    1. STRONG BUY  — upside ≥ +30% AND composite ≥ 70
    2. BUY         — upside ≥ +10% AND composite ≥ 55
    3. STRONG SELL — upside ≤ −30%
    4. SELL        — upside ≤ −15%
    5. HOLD        — anything else

Confidence is the aggregator's own ``confidence`` (high / medium / low).
A ``low`` confidence downgrades STRONG BUY → BUY and STRONG SELL → SELL,
since it usually means the 5 valuation models disagree wildly.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal

from core.constants import RATING_THRESHOLDS


Verdict = Literal["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"]


# ============================================================
# Result
# ============================================================
@dataclass
class Rating:
    verdict: Verdict
    composite: float
    upside: float                       # decimal (0.30 = +30%)
    confidence: str                     # "high" | "medium" | "low"
    reasoning: str

    @property
    def color(self) -> str:
        return _COLORS[self.verdict]


_COLORS: dict[str, str] = {
    "STRONG BUY":  "var(--gains)",
    "BUY":         "var(--gains)",
    "HOLD":        "var(--accent)",
    "SELL":        "var(--losses)",
    "STRONG SELL": "var(--losses)",
}


# ============================================================
# Public API
# ============================================================
def rate(
    *,
    composite: float,
    upside: Optional[float],
    confidence: str = "high",
) -> Rating:
    """
    Args:
        composite:   weighted score in 0-100 (from ScoreBreakdown.composite)
        upside:      (intrinsic − price) / price; None if not computable
        confidence:  "high" | "medium" | "low" (from AggregatedValuation)
    """
    t = RATING_THRESHOLDS

    if upside is None:
        verdict: Verdict = "HOLD"
        reasoning = (
            f"Composite {composite:.0f} but no aggregator upside available — "
            "defaulting to HOLD."
        )
    elif upside >= t["strong_buy_upside"] and composite >= t["strong_buy_score"]:
        verdict = "STRONG BUY"
        reasoning = (
            f"Upside {upside:+.1%} ≥ {t['strong_buy_upside']:+.0%} "
            f"and composite {composite:.0f} ≥ {t['strong_buy_score']:.0f}."
        )
    elif upside >= t["buy_upside"] and composite >= t["buy_score"]:
        verdict = "BUY"
        reasoning = (
            f"Upside {upside:+.1%} ≥ {t['buy_upside']:+.0%} "
            f"and composite {composite:.0f} ≥ {t['buy_score']:.0f}."
        )
    elif upside <= t["strong_sell_upside"]:
        verdict = "STRONG SELL"
        reasoning = (
            f"Upside {upside:+.1%} ≤ {t['strong_sell_upside']:+.0%} — "
            "stock trades far above any reasonable intrinsic estimate."
        )
    elif upside <= t["sell_upside"]:
        verdict = "SELL"
        reasoning = (
            f"Upside {upside:+.1%} ≤ {t['sell_upside']:+.0%} — "
            "intrinsic value sits below the current price."
        )
    else:
        verdict = "HOLD"
        reasoning = (
            f"Upside {upside:+.1%} and composite {composite:.0f} are in the "
            "no-action band."
        )

    if confidence == "low":
        if verdict == "STRONG BUY":
            verdict = "BUY"
            reasoning += " Downgraded from STRONG BUY due to LOW confidence (model dispersion)."
        elif verdict == "STRONG SELL":
            verdict = "SELL"
            reasoning += " Downgraded from STRONG SELL due to LOW confidence (model dispersion)."

    return Rating(
        verdict=verdict,
        composite=float(composite),
        upside=float(upside if upside is not None else 0.0),
        confidence=confidence,
        reasoning=reasoning,
    )
