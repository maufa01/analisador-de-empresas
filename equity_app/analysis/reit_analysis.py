"""
REIT-specific metrics — FFO, AFFO, dividend yield, P/FFO. Driven by
SEC EDGAR Company Facts.

FFO (NAREIT definition):
    FFO = Net Income + Real-Estate Depreciation - Gain on Sale of Properties
We approximate "real-estate depreciation" with reported depreciation — for
the vast majority of REITs that's a few percent off, never directionally wrong.

AFFO = FFO − recurring CapEx (cash for property maintenance), more
conservative because it deducts the cash that has to keep going back into
the buildings.
"""
from __future__ import annotations
from typing import Optional

import logging

from data.sector_specific_concepts import (
    REIT_INCOME_CONCEPTS, REIT_BALANCE_CONCEPTS, REIT_CASHFLOW_CONCEPTS,
)

logger = logging.getLogger(__name__)


def _facts_for(ticker: str) -> dict:
    try:
        from data.edgar_provider import get_company_facts
        return get_company_facts(ticker) or {}
    except Exception:
        return {}


def _latest_annual_value(facts: dict, aliases: list[str]) -> Optional[float]:
    if not facts or "facts" not in facts:
        return None
    gaap = facts["facts"].get("us-gaap", {})
    for alias in aliases:
        node = gaap.get(alias)
        if not node:
            continue
        for unit_key in ("USD", "shares", "USD/shares"):
            entries = node.get("units", {}).get(unit_key)
            if not entries:
                continue
            annual = [
                e for e in entries
                if e.get("form") == "10-K" and e.get("fp") == "FY"
            ]
            if not annual:
                continue
            annual.sort(key=lambda e: e.get("end", ""), reverse=True)
            val = annual[0].get("val")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
    return None


def analyze_reit(
    ticker: str, *,
    market_cap: Optional[float] = None,
    current_price: Optional[float] = None,
) -> dict:
    """REIT metrics from SEC Company Facts. Optional market_cap / price
    populate P/FFO and dividend yield."""
    facts = _facts_for(ticker)
    if not facts:
        return {
            "available": False,
            "note": "SEC EDGAR returned no Company Facts for this ticker.",
        }

    def L(group: dict[str, list[str]], key: str) -> Optional[float]:
        return _latest_annual_value(facts, group.get(key, []))

    rental_income = L(REIT_INCOME_CONCEPTS, "rental_income")
    op_expenses  = L(REIT_INCOME_CONCEPTS, "operating_expenses")
    depreciation = L(REIT_INCOME_CONCEPTS, "depreciation")
    net_income   = L(REIT_INCOME_CONCEPTS, "net_income")
    gain_on_sale = L(REIT_INCOME_CONCEPTS, "gain_on_sale") or 0.0
    capex        = L(REIT_CASHFLOW_CONCEPTS, "capex") or 0.0
    div_paid     = L(REIT_CASHFLOW_CONCEPTS, "dividends_paid") or 0.0

    # Shares — try diluted from income concepts; final fallback is
    # CommonStockSharesOutstanding picked up from any GAAP concept.
    shares = L(REIT_INCOME_CONCEPTS, "shares_diluted")
    if shares is None:
        shares = _latest_annual_value(facts, ["CommonStockSharesOutstanding"])

    real_estate_inv = L(REIT_BALANCE_CONCEPTS, "real_estate_investments")
    total_assets    = L(REIT_BALANCE_CONCEPTS, "total_assets")
    total_equity    = L(REIT_BALANCE_CONCEPTS, "total_equity")

    # FFO = NI + Depreciation − Gain on sale
    ffo: Optional[float] = None
    if net_income is not None and depreciation is not None:
        ffo = net_income + depreciation - abs(gain_on_sale)

    # AFFO = FFO − recurring capex (capex on cashflow is reported negative)
    affo: Optional[float] = None
    if ffo is not None:
        affo = ffo - abs(capex)

    ffo_per_share  = (ffo  / shares) if (ffo  is not None and shares) else None
    affo_per_share = (affo / shares) if (affo is not None and shares) else None

    p_ffo = None
    if current_price and ffo_per_share and ffo_per_share > 0:
        p_ffo = current_price / ffo_per_share

    div_yield = None
    if market_cap and div_paid:
        div_yield = abs(div_paid) / market_cap

    payout_of_ffo = None
    if ffo and div_paid:
        payout_of_ffo = abs(div_paid) / ffo

    return {
        "available":            True,
        "rental_income":        rental_income,
        "operating_expenses":   op_expenses,
        "depreciation":         depreciation,
        "net_income":           net_income,
        "gain_on_sale":         gain_on_sale,
        "capex":                capex,
        "dividends_paid":       div_paid,
        "shares":               shares,
        "real_estate_invested": real_estate_inv,
        "total_assets":         total_assets,
        "total_equity":         total_equity,
        "ffo":                  ffo,
        "affo":                 affo,
        "ffo_per_share":        ffo_per_share,
        "affo_per_share":       affo_per_share,
        "p_ffo":                p_ffo,
        "dividend_yield":       div_yield,
        "payout_of_ffo":        payout_of_ffo,
        "note": (
            "FFO ≈ NI + Depreciation − Gains on sale. AFFO ≈ FFO − recurring "
            "capex. NAREIT-aligned approximation; some REITs report a more "
            "precise normalised FFO in their supplementals."
        ),
    }
