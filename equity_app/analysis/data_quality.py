"""
Detect partial financial-statement loads and (when possible) heal them.

A common failure mode: SEC EDGAR / yfinance returns an income statement
DataFrame with the `revenue` column missing (different XBRL labels,
rate-limited partial response, etc.). Downstream ratios like ROIC
survive because they don't depend on revenue, but Revenue and Net
Margin silently render as `—`.

Two-step recovery:

1. :func:`heal_income_statement` — try to reconstruct missing critical
   fields from sibling fields (e.g. ``revenue = grossProfit + costOfRevenue``).
2. :func:`require_complete_income` — if the healed frame is still
   incomplete, fall through a provider chain.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from analysis.ratios import _get


CRITICAL_INCOME_FIELDS = ["revenue", "net_income", "operating_income"]
CRITICAL_BALANCE_FIELDS = ["total_assets", "total_equity"]
CRITICAL_CASH_FIELDS = ["ocf"]


@dataclass
class CompletenessReport:
    is_complete: bool
    missing: list[str]
    available: list[str]


# ============================================================
# Completeness probes
# ============================================================
def _assess(df: pd.DataFrame, fields: list[str]) -> CompletenessReport:
    missing = [f for f in fields if _get(df, f) is None]
    available = [f for f in fields if _get(df, f) is not None]
    return CompletenessReport(
        is_complete=(len(missing) == 0),
        missing=missing,
        available=available,
    )


def assess_income_completeness(income: pd.DataFrame) -> CompletenessReport:
    return _assess(income, CRITICAL_INCOME_FIELDS)


def assess_balance_completeness(balance: pd.DataFrame) -> CompletenessReport:
    return _assess(balance, CRITICAL_BALANCE_FIELDS)


def assess_cash_completeness(cash: pd.DataFrame) -> CompletenessReport:
    return _assess(cash, CRITICAL_CASH_FIELDS)


# ============================================================
# Healing
# ============================================================
# SEC EDGAR ships revenue under any of these XBRL element names —
# the FMP-shape ``revenue`` / ``totalRevenue`` are not always present.
# Extended in P12.A3 to cover utility-specific elements (DUK, SO, NEE
# all ship revenue under RegulatedAndUnregulatedOperatingRevenue or the
# more granular ElectricUtilityRevenue / GasUtilityRevenue).
_REVENUE_XBRL_ALIASES = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
    "OperatingRevenue",
    "Sales",
    # Utility-specific
    "RegulatedAndUnregulatedOperatingRevenue",
    "ElectricUtilityRevenue",
    "GasUtilityRevenue",
)


def heal_income_statement(income: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct missing critical fields from siblings, when possible.

    - ``revenue``          ← any SEC EDGAR XBRL alias, then
                             ``grossProfit + costOfRevenue``
    - ``operating_income`` ← ``grossProfit − operatingExpenses``
    - ``ebitda``           ← ``operatingIncome + depreciationAndAmortization``
                             for years where FMP's native ``ebitda`` is
                             missing (FMP only started reporting it
                             consistently in 2023)
    - ``incomeBeforeTax``  ← ``netIncome + incomeTaxExpense`` when missing
    """
    if income is None or income.empty:
        return income
    df = income.copy()

    # ---- Revenue ----
    if "revenue" not in df.columns and "totalRevenue" not in df.columns:
        # 1) try the SEC EDGAR XBRL aliases first (real reported field
        #    under a different element name)
        for alias in _REVENUE_XBRL_ALIASES:
            if alias in df.columns:
                df["revenue"] = df[alias]
                break
        # 2) last resort: gross profit + cost of revenue
        if "revenue" not in df.columns:
            if "grossProfit" in df.columns and "costOfRevenue" in df.columns:
                df["revenue"] = df["grossProfit"] + df["costOfRevenue"]

    # ---- Operating income (path 1: gross profit − opex) ----
    if (_get(df, "operating_income") is None
            and "grossProfit" in df.columns
            and "operatingExpenses" in df.columns):
        df["operatingIncome"] = df["grossProfit"] - df["operatingExpenses"]

    # ---- Pretax income from NI + tax expense ----
    if ("incomeBeforeTax" not in df.columns
            and "netIncome" in df.columns
            and "incomeTaxExpense" in df.columns):
        df["incomeBeforeTax"] = df["netIncome"] + df["incomeTaxExpense"]

    # ---- Operating income (path 2: pretax + interest expense) ----
    # Utilities sometimes ship NI + tax + interest but no operatingIncome.
    # Must run BEFORE the EBITDA step so EBITDA can use the reconstructed
    # operatingIncome.
    if ("operatingIncome" not in df.columns
            and "incomeBeforeTax" in df.columns
            and "interestExpense" in df.columns):
        df["operatingIncome"] = (
            df["incomeBeforeTax"] + df["interestExpense"].fillna(0.0)
        )
        if "ebit" not in df.columns:
            df["ebit"] = df["operatingIncome"]

    # ---- EBITDA (operating income + D&A for missing years) ----
    if ("operatingIncome" in df.columns
            and "depreciationAndAmortization" in df.columns):
        op_inc = df["operatingIncome"]
        da = df["depreciationAndAmortization"].fillna(0.0)
        reconstructed = op_inc + da
        existing = df.get("ebitda")
        if existing is not None:
            # Only fill the rows where source EBITDA is missing
            df["ebitda"] = existing.fillna(reconstructed)
        else:
            df["ebitda"] = reconstructed

    return df


# ============================================================
# Public: combined check + recovery
# ============================================================
def require_complete_income(
    ticker: str,
    income: pd.DataFrame,
    source: str,
    *,
    fallback_chain: Optional[list[Callable[[str], object]]] = None,
) -> tuple[pd.DataFrame, str]:
    """Return ``(income_df, source_name)`` — the most complete income
    statement we can produce for the ticker.

    1. If the loaded statement is already complete, return it.
    2. Try healing it from sibling fields.
    3. Walk the optional fallback chain (each entry is a callable
       returning a ``FinancialsBundle``-shaped object with ``.income``
       and ``.source`` attributes).
    4. Best-effort: return whatever we have.
    """
    rep = assess_income_completeness(income)
    if rep.is_complete:
        return income, source

    healed = heal_income_statement(income)
    if assess_income_completeness(healed).is_complete:
        return healed, f"{source} (healed)"

    for fn in (fallback_chain or []):
        try:
            alt = fn(ticker)
        except Exception:
            continue
        if alt is None or not hasattr(alt, "income") or alt.income is None:
            continue
        if assess_income_completeness(alt.income).is_complete:
            return alt.income, getattr(alt, "source", "unknown")

    return healed, source
