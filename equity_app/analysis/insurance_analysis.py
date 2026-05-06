"""
Insurance-specific metrics from SEC EDGAR Company Facts:
premium revenue, investment income, policyholder benefits and a
simple combined-ratio approximation. Same shape as bank_analysis /
reit_analysis: returns a dict with ``available`` and a ``note``.
"""
from __future__ import annotations
from typing import Optional

import logging

from data.sector_specific_concepts import INSURANCE_INCOME_CONCEPTS

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


def analyze_insurance(ticker: str) -> dict:
    facts = _facts_for(ticker)
    if not facts:
        return {
            "available": False,
            "note": "SEC EDGAR returned no Company Facts for this ticker.",
        }

    def L(key: str) -> Optional[float]:
        return _latest_annual_value(facts, INSURANCE_INCOME_CONCEPTS.get(key, []))

    premium = L("premium_revenue")
    investment_income = L("investment_income")
    policyholder_benefits = L("policyholder_benefits")
    underwriting_expense = L("underwriting_expense")
    net_income = L("net_income")

    # Combined ratio ≈ (Benefits + Underwriting expense) / Premiums
    # (simplified — true combined ratio uses LR + ER from regulatory reports)
    combined_ratio = None
    if premium and policyholder_benefits is not None:
        denom = premium
        numer = (policyholder_benefits or 0.0) + (underwriting_expense or 0.0)
        if denom > 0:
            combined_ratio = numer / denom

    # Float / book value not derivable cleanly from company facts alone —
    # left for a more focused parser. Surface investment yield instead:
    total_assets = _latest_annual_value(facts, ["Assets"])
    total_equity = _latest_annual_value(facts, ["StockholdersEquity"])
    investment_yield = (
        investment_income / total_assets
        if (investment_income is not None and total_assets) else None
    )
    roe = (net_income / total_equity) if (net_income is not None and total_equity) else None

    return {
        "available":           True,
        "premium_revenue":     premium,
        "investment_income":   investment_income,
        "policyholder_benefits": policyholder_benefits,
        "underwriting_expense": underwriting_expense,
        "net_income":          net_income,
        "total_assets":        total_assets,
        "total_equity":        total_equity,
        "combined_ratio":      combined_ratio,
        "investment_yield":    investment_yield,
        "roe":                 roe,
        "note": (
            "Approximate combined ratio = (Benefits + Underwriting Expense) / "
            "Premiums. True LR + ER decomposition lives in regulatory filings."
        ),
    }
