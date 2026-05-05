"""
AI investment-thesis prompt generator — offline (no API calls).

Bundles every result the page already computed (DCF / score / EQ /
balance-sheet quality / etc.) into a JSON payload, then wraps it in an
analyst-style prompt template the user can paste into Claude or GPT
externally.

When ``ANTHROPIC_API_KEY`` is wired later, swap the inner call to send
the prompt directly and stream the response — the bundle structure
stays the same.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any

import json

import pandas as pd


# ============================================================
# Result
# ============================================================
@dataclass
class ThesisPrompt:
    ticker: str
    bundle: dict                                # serialisable analysis payload
    prompt: str                                 # ready-to-paste prompt
    n_chars: int
    n_words: int
    estimated_input_tokens: int
    estimated_cost_sonnet_usd: float            # input cost only — output unknown


# ============================================================
# Prompt template
# ============================================================
PROMPT_TEMPLATE = """You are a senior equity research analyst. Generate an institutional-quality investment thesis grounded strictly in the quantitative analysis below.

COMPANY DATA (JSON):
{company_data}

OUTPUT FORMAT (markdown):

## Executive Summary
3–5 bullet points capturing the essence. Each bullet must reference a specific number from the data. No vague statements.

## Key Strengths
Top 3 quantifiable strengths with evidence. Format:
- **[Strength title]**: [Evidence with specific numbers]

## Key Risks
Top 3 risks with evidence. Be specific. Format:
- **[Risk title]**: [Evidence with specific numbers]

## Bull Case (1 paragraph)
What needs to happen for the stock to outperform significantly. Be specific about catalysts and the metrics that would have to change.

## Bear Case (1 paragraph)
What could go wrong. Reference the stress-test scenarios in the data.

## Catalyst Calendar
Upcoming events in the next 6–12 months that could move the stock.

## Final Recommendation
Rating: [STRONG BUY / BUY / HOLD / SELL / STRONG SELL]
Confidence: [HIGH / MEDIUM / LOW]
Time horizon: [SHORT (<6m) / MEDIUM (6–18m) / LONG (>18m)]
Position sizing suggestion: [as % of portfolio]

## Caveats
What we don't know. Limitations of this analysis. Be honest.

CONSTRAINTS:
- Stay grounded in the data provided. Don't fabricate.
- Reference specific numbers, not generalisations.
- Avoid generic phrases ("solid company", "good prospects").
- Match the rating to the data — if upside is negative, this is not a BUY.
- 800–1200 words total.
- If data is incomplete or contradictory, say so. Don't be more confident than the data warrants.
"""


# ============================================================
# Bundle builder
# ============================================================
def _coerce(v: Any) -> Any:
    """Make any analysis dataclass JSON-friendly. Drops dataframes."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, pd.DataFrame):
        # Skip dataframes — they balloon the prompt size
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    if isinstance(v, dict):
        return {k: _coerce(x) for k, x in v.items()}
    if hasattr(v, "__dict__"):
        return {k: _coerce(x) for k, x in v.__dict__.items()
                if not k.startswith("_")}
    try:
        return str(v)
    except Exception:
        return None


def _section(name: str, payload: Optional[Any]) -> tuple[str, Any]:
    if payload is None:
        return name, None
    return name, _coerce(payload)


def build_bundle(
    *,
    ticker: str,
    company_name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    market_cap: Optional[float] = None,
    current_price: Optional[float] = None,
    valuation_results=None,            # core.valuation_pipeline.ValuationResults
    earnings_quality=None,             # analysis.earnings_quality.EarningsQuality
    ccc=None,                          # analysis.working_capital.CCCResult
    balance_sheet=None,                # analysis.balance_sheet_quality.BalanceSheetQuality
    revenue_quality=None,              # analysis.revenue_quality.RevenueQuality
    earnings_volatility=None,          # analysis.earnings_volatility.EarningsVolatility
    dividend_safety=None,              # analysis.dividend_safety.DividendSafetyResult
    shareholder_yield=None,            # analysis.shareholder_yield.ShareholderYield
    capital_allocation=None,
    peer_ranking=None,
    rates_stress=None,
    recession_stress=None,
    sector_stress=None,
    news_sentiment=None,
) -> dict:
    """All inputs optional — pass whatever the page has computed."""
    bundle: dict = {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "market_cap": market_cap,
        "current_price": current_price,
    }

    if valuation_results is not None:
        v = valuation_results
        bundle["valuation"] = {
            "wacc": _coerce(getattr(v, "wacc", None)),
            "dcf_intrinsic": (v.dcf.intrinsic_value_per_share
                              if getattr(v, "dcf", None) else None),
            "comparables_intrinsic": (
                v.comparables.implied_per_share_median
                if getattr(v, "comparables", None) else None),
            "monte_carlo_median": (
                v.monte_carlo.median if getattr(v, "monte_carlo", None) else None),
            "ddm_intrinsic": (
                v.ddm.intrinsic_value_per_share if getattr(v, "ddm", None) else None),
            "residual_income_intrinsic": (
                v.residual_income.intrinsic_value_per_share
                if getattr(v, "residual_income", None) else None),
            "aggregator_intrinsic": (
                v.aggregator.intrinsic_per_share
                if getattr(v, "aggregator", None) else None),
            "score_composite": (
                v.score.composite if getattr(v, "score", None) else None),
            "rating_verdict": (
                v.rating.verdict if getattr(v, "rating", None) else None),
            "rating_upside": (
                v.rating.upside if getattr(v, "rating", None) else None),
            "rating_confidence": (
                v.rating.confidence if getattr(v, "rating", None) else None),
        }

    for name, payload in [
        _section("earnings_quality",     earnings_quality),
        _section("cash_conversion_cycle", ccc),
        _section("balance_sheet_quality", balance_sheet),
        _section("revenue_quality",      revenue_quality),
        _section("earnings_volatility",  earnings_volatility),
        _section("dividend_safety",      dividend_safety),
        _section("shareholder_yield",    shareholder_yield),
        _section("capital_allocation",   capital_allocation),
        _section("peer_ranking",         peer_ranking),
        _section("stress_rates",         rates_stress),
        _section("stress_recession",     recession_stress),
        _section("stress_sector",        sector_stress),
        _section("news_sentiment",       news_sentiment),
    ]:
        if payload is not None:
            bundle[name] = payload

    return bundle


# ============================================================
# Public API
# ============================================================
# Anthropic Sonnet input pricing (USD per million tokens) — adjust if it changes.
_SONNET_INPUT_USD_PER_MTOK = 3.0


def build_thesis_prompt(*, ticker: str, **kwargs) -> ThesisPrompt:
    bundle = build_bundle(ticker=ticker, **kwargs)
    payload_json = json.dumps(bundle, indent=2, default=str)
    prompt = PROMPT_TEMPLATE.format(company_data=payload_json)

    n_chars = len(prompt)
    n_words = len(prompt.split())
    # 4-chars-per-token is a conservative rule of thumb; underestimates code,
    # overestimates prose. Good enough for cost preview.
    n_tokens = n_chars // 4
    cost = (n_tokens / 1_000_000.0) * _SONNET_INPUT_USD_PER_MTOK

    return ThesisPrompt(
        ticker=ticker,
        bundle=bundle,
        prompt=prompt,
        n_chars=n_chars,
        n_words=n_words,
        estimated_input_tokens=n_tokens,
        estimated_cost_sonnet_usd=cost,
    )
