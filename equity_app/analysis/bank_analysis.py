"""
Bank-specific metrics — Net Interest Income, NIM, Efficiency Ratio,
loans, deposits, capital. Pulls from SEC EDGAR Company Facts via the
bank GAAP-concept aliases in ``data.sector_specific_concepts``.

Returns a dict the UI consumes via ``ui.components.views.bank_view``.
Empty values bubble up as ``None`` — render as "—" upstream.
"""
from __future__ import annotations
from typing import Optional

import logging

from data.sector_specific_concepts import (
    BANK_INCOME_CONCEPTS, BANK_BALANCE_CONCEPTS,
)

logger = logging.getLogger(__name__)


def _facts_for(ticker: str) -> dict:
    try:
        from data.edgar_provider import get_company_facts
        return get_company_facts(ticker) or {}
    except Exception:
        return {}


def _latest_annual_value(facts: dict, aliases: list[str]) -> Optional[float]:
    """First annual (10-K, FY) value from any matching XBRL alias."""
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
            # Most-recent end first
            annual.sort(key=lambda e: e.get("end", ""), reverse=True)
            val = annual[0].get("val")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
    return None


def analyze_bank(ticker: str) -> dict:
    """Bank-specific metrics from SEC Company Facts."""
    facts = _facts_for(ticker)
    if not facts:
        return {
            "available": False,
            "note": "SEC EDGAR returned no Company Facts for this ticker.",
        }

    def L(key: str) -> Optional[float]:
        aliases = BANK_INCOME_CONCEPTS.get(key) or BANK_BALANCE_CONCEPTS.get(key) or []
        return _latest_annual_value(facts, aliases)

    interest_income = L("interest_income")
    interest_expense = L("interest_expense")
    nii_reported = L("net_interest_income")
    nii = (nii_reported
           if nii_reported is not None
           else (interest_income - interest_expense
                 if interest_income is not None and interest_expense is not None
                 else None))

    provision = L("provision_for_loan_losses")
    noninterest_income = L("noninterest_income")
    noninterest_expense = L("noninterest_expense")
    net_income = L("net_income")

    total_loans = L("total_loans")
    total_deposits = L("total_deposits")
    total_assets = L("total_assets")
    total_equity = L("total_equity")

    # NIM ≈ Net Interest Income / Avg Earning Assets — total_assets is a proxy
    # (true earning-assets number requires balance-sheet detail).
    nim = (nii / total_assets) if (nii and total_assets) else None

    # Efficiency = Noninterest Expense / (NII + Noninterest Income)
    efficiency = None
    if noninterest_expense is not None and nii is not None:
        denom = nii + (noninterest_income or 0.0)
        if denom > 0:
            efficiency = noninterest_expense / denom

    # Loan / Deposit ratio
    loan_to_deposit = None
    if total_loans and total_deposits:
        loan_to_deposit = total_loans / total_deposits

    # ROE / ROA from net income
    roe = (net_income / total_equity) if (net_income is not None and total_equity) else None
    roa = (net_income / total_assets) if (net_income is not None and total_assets) else None

    return {
        "available":          True,
        "interest_income":    interest_income,
        "interest_expense":   interest_expense,
        "net_interest_income": nii,
        "provision_for_loan_losses": provision,
        "noninterest_income":  noninterest_income,
        "noninterest_expense": noninterest_expense,
        "net_income":          net_income,
        "total_loans":         total_loans,
        "total_deposits":      total_deposits,
        "total_assets":        total_assets,
        "total_equity":        total_equity,
        "nim":                 nim,
        "efficiency_ratio":    efficiency,
        "loan_to_deposit":     loan_to_deposit,
        "roe":                 roe,
        "roa":                 roa,
        "note": (
            "Bank-specific metrics from SEC Company Facts. NIM uses total "
            "assets as a proxy for earning assets — true NIM lives in the "
            "regulatory call report (FFIEC 031/041)."
        ),
    }
