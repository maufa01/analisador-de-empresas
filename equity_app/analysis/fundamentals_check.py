"""
Coherence validation for company financials.

We do NOT trust provider data blindly. Before any model touches a
``CompanyData``, we walk a checklist:

1. Balance sheet identity:    Assets == Liabilities + Equity (within tolerance)
2. Cash reconciliation:       ΔCash ≈ CFO + CFI + CFF
3. Index integrity:           strictly increasing dates, no duplicates
4. Critical-field presence:   revenue, total_assets, OCF must be non-null
5. Sign sanity:               assets > 0, revenue > 0

Each check produces an Issue with severity. Severity ladder:
- ``info``    — informational, model can run as-is
- ``warning`` — model can run but show disclaimer
- ``error``   — model should be skipped on this data
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal

import pandas as pd

from .ratios import _get


Severity = Literal["info", "warning", "error"]


@dataclass
class Issue:
    code: str
    severity: Severity
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class CoherenceReport:
    is_valid: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    def by_severity(self, severity: Severity) -> list[Issue]:
        return [i for i in self.issues if i.severity == severity]


# ============================================================
# Individual checks
# ============================================================
def check_balance_sheet_identity(
    balance: pd.DataFrame, *, tolerance_pct: float = 0.01
) -> Optional[Issue]:
    """Assets = Liabilities + Equity (within ``tolerance_pct`` of TA)."""
    ta = _get(balance, "total_assets")
    tl = _get(balance, "total_liabilities")
    te = _get(balance, "total_equity")
    if ta is None or te is None:
        return None
    # If liabilities not reported, derive: TL = TA - TE
    if tl is None:
        return None

    last_idx = ta.dropna().index.intersection(te.dropna().index).intersection(tl.dropna().index)
    if last_idx.empty:
        return None
    i = last_idx.max()
    a, l_val, e = float(ta[i]), float(tl[i]), float(te[i])
    diff = a - (l_val + e)
    if a == 0:
        return None
    rel = abs(diff) / abs(a)
    if rel > tolerance_pct:
        return Issue(
            code="BS_IDENTITY_VIOLATION",
            severity="warning" if rel < 0.05 else "error",
            message=(
                f"Balance sheet does not balance for {i.date()}: "
                f"A={a:,.0f}, L+E={l_val+e:,.0f}, diff={diff:,.0f} "
                f"({rel:.2%} of A)"
            ),
            details={"period": str(i.date()), "diff": diff, "rel": rel},
        )
    return None


def check_cash_reconciliation(
    cash: pd.DataFrame, balance: pd.DataFrame, *, tolerance_pct: float = 0.10
) -> Optional[Issue]:
    """
    Net cash change ≈ CFO + CFI + CFF.

    Wide tolerance because providers don't always carry every cash-flow
    line and ΔCash often includes FX effects we don't model here.
    """
    cfo = _get(cash, "ocf")
    cash_eq = _get(balance, "cash_eq")
    # CFI/CFF aliases — try common names
    cfi = None
    cff = None
    for col in ("netCashUsedForInvestingActivites", "netCashUsedForInvestingActivities"):
        if col in cash.columns:
            cfi = cash[col].astype(float); break
    for col in (
        "netCashUsedProvidedByFinancingActivities",
        "netCashProvidedByUsedInFinancingActivities",
    ):
        if col in cash.columns:
            cff = cash[col].astype(float); break

    if cfo is None or cfi is None or cff is None or cash_eq is None:
        return None
    if len(cash_eq.dropna()) < 2:
        return None

    cash_dropped = cash_eq.dropna()
    delta_cash = float(cash_dropped.iloc[-1] - cash_dropped.iloc[-2])
    cfo_t = float(cfo.dropna().iloc[-1])
    cfi_t = float(cfi.dropna().iloc[-1])
    cff_t = float(cff.dropna().iloc[-1])
    expected = cfo_t + cfi_t + cff_t
    if abs(delta_cash) < 1:
        return None
    diff = delta_cash - expected
    rel = abs(diff) / max(abs(delta_cash), 1.0)
    if rel > tolerance_pct:
        return Issue(
            code="CASH_RECONCILIATION_DRIFT",
            severity="info" if rel < 0.30 else "warning",
            message=(
                f"Cash flow does not reconcile to balance-sheet cash delta: "
                f"ΔCash={delta_cash:,.0f}, CFO+CFI+CFF={expected:,.0f}, "
                f"diff={diff:,.0f} ({rel:.2%})"
            ),
            details={"delta_cash": delta_cash, "sum_cf": expected, "rel": rel},
        )
    return None


def check_index_integrity(df: pd.DataFrame, name: str) -> Optional[Issue]:
    if df is None or df.empty:
        return None
    if df.index.duplicated().any():
        return Issue(
            code="INDEX_DUPLICATE",
            severity="error",
            message=f"{name} has duplicate index entries",
        )
    if not df.index.is_monotonic_increasing:
        return Issue(
            code="INDEX_NOT_SORTED",
            severity="warning",
            message=f"{name} index is not monotonically increasing",
        )
    return None


def check_critical_fields(
    income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame
) -> list[Issue]:
    issues: list[Issue] = []
    rev = _get(income, "revenue")
    ta = _get(balance, "total_assets")
    cfo = _get(cash, "ocf")
    if rev is None or rev.dropna().empty:
        issues.append(Issue("MISSING_REVENUE", "error", "Revenue missing"))
    if ta is None or ta.dropna().empty:
        issues.append(Issue("MISSING_TOTAL_ASSETS", "error", "Total Assets missing"))
    if cfo is None or cfo.dropna().empty:
        issues.append(Issue("MISSING_OCF", "warning", "Operating Cash Flow missing"))
    return issues


def check_sign_sanity(income: pd.DataFrame, balance: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    rev = _get(income, "revenue")
    ta = _get(balance, "total_assets")
    if rev is not None and not rev.dropna().empty and float(rev.dropna().iloc[-1]) <= 0:
        issues.append(Issue(
            "REVENUE_NON_POSITIVE", "error",
            f"Revenue is non-positive: {float(rev.dropna().iloc[-1]):,.0f}",
        ))
    if ta is not None and not ta.dropna().empty and float(ta.dropna().iloc[-1]) <= 0:
        issues.append(Issue(
            "ASSETS_NON_POSITIVE", "error",
            f"Total Assets non-positive: {float(ta.dropna().iloc[-1]):,.0f}",
        ))
    return issues


# ============================================================
# Aggregator
# ============================================================
def coherence_report(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> CoherenceReport:
    issues: list[Issue] = []

    issues.extend(check_critical_fields(income, balance, cash))
    issues.extend(check_sign_sanity(income, balance))
    for df, name in [(income, "income"), (balance, "balance"), (cash, "cash")]:
        i = check_index_integrity(df, name)
        if i is not None:
            issues.append(i)

    bs_issue = check_balance_sheet_identity(balance)
    if bs_issue is not None:
        issues.append(bs_issue)

    cash_issue = check_cash_reconciliation(cash, balance)
    if cash_issue is not None:
        issues.append(cash_issue)

    is_valid = not any(i.severity == "error" for i in issues)
    return CoherenceReport(is_valid=is_valid, issues=issues)
