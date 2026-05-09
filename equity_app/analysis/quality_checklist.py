"""
Phil Town / Pat Dorsey style yes-no quality checks.

Each check returns a :class:`QualityCheck` whose ``result`` is True,
False, or None (None = data insufficient). The UI groups them by
``category`` and renders a SI / NO / N/A pill plus the supporting
numbers.

Add new checks by writing a pure function ``(income, balance, cash)
→ QualityCheck`` and appending it to :data:`ALL_CHECKS` — the runner
orchestrates the rest.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow, cagr


# ============================================================
# Dataclasses
# ============================================================
@dataclass
class QualityCheck:
    label: str
    result: Optional[bool]              # None = not calculable
    detail: str
    weight: float = 1.0
    category: str = "general"           # growth | profitability | capital_allocation


@dataclass
class ChecklistResult:
    checks: list[QualityCheck]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.result is True)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.result is False)

    @property
    def applicable(self) -> int:
        return sum(1 for c in self.checks if c.result is not None)

    @property
    def score(self) -> float:
        n = self.applicable
        return 0.0 if n == 0 else (self.passed / n) * 100.0


# ============================================================
# Internals
# ============================================================
def _na(label: str, reason: str, *, category: str = "general") -> QualityCheck:
    return QualityCheck(label, None, reason, category=category)


def _both_finite(*values: float) -> bool:
    return all(np.isfinite(v) for v in values)


# ============================================================
# Individual checks (each one is a pure function)
# ============================================================
def check_revenue_accelerating(income, balance, cash) -> QualityCheck:
    """Revenue growth accelerating: 3Y CAGR > 5Y CAGR (with 50bp threshold)."""
    label = "Revenue growth is accelerating"
    rev = _get(income, "revenue")
    if rev is None or len(rev.dropna()) < 6:
        return _na(label, "Insufficient data (need 6+ years)", category="growth")
    cagr_3y = cagr(rev, periods=3)
    cagr_5y = cagr(rev, periods=5)
    if not _both_finite(cagr_3y, cagr_5y):
        return _na(label, "CAGR not computable", category="growth")
    return QualityCheck(
        label,
        bool(cagr_3y > cagr_5y + 0.005),
        f"3Y CAGR {cagr_3y*100:+.1f}% vs 5Y CAGR {cagr_5y*100:+.1f}%",
        category="growth",
    )


def check_op_income_outpaces_revenue(income, balance, cash) -> QualityCheck:
    """Operating leverage: op-income CAGR > revenue CAGR (margin expansion)."""
    label = "Operating income grows faster than revenue"
    rev = _get(income, "revenue")
    op = _get(income, "operating_income")
    if rev is None or op is None:
        return _na(label, "Missing revenue or operating income",
                   category="profitability")
    rev_cagr = cagr(rev, periods=5)
    op_cagr = cagr(op, periods=5)
    if not _both_finite(rev_cagr, op_cagr):
        return _na(label, "CAGR not computable", category="profitability")
    return QualityCheck(
        label,
        bool(op_cagr > rev_cagr),
        f"Op income 5Y CAGR {op_cagr*100:+.1f}% vs Revenue 5Y CAGR {rev_cagr*100:+.1f}%",
        category="profitability",
    )


def check_high_margin_business(income, balance, cash) -> QualityCheck:
    """Gross margin > 40% (heuristic for moat-grade businesses)."""
    label = "High-margin business (gross margin > 40%)"
    rev = _get(income, "revenue")
    gross = _get(income, "gross_profit")
    if rev is None or gross is None:
        return _na(label, "Missing data", category="profitability")
    margin = (gross / rev.replace(0, np.nan)).dropna().tail(3)
    if margin.empty:
        return _na(label, "Margin not computable", category="profitability")
    avg = float(margin.mean())
    if not np.isfinite(avg):
        return _na(label, "Margin not computable", category="profitability")
    return QualityCheck(
        label,
        bool(avg > 0.40),
        f"Avg 3Y gross margin: {avg*100:.1f}% (threshold 40%)",
        category="profitability",
    )


def check_buybacks_exceed_issuance(income, balance, cash) -> QualityCheck:
    """Net share count is decreasing over the loaded history."""
    label = "Buybacks exceed issuance (net shares declining)"
    shares = _get(income, "weighted_avg_shares")
    if shares is None or len(shares.dropna()) < 3:
        return _na(label, "Missing share-count history",
                   category="capital_allocation")
    s = shares.dropna()
    change = (s.iloc[-1] / s.iloc[0]) - 1.0
    return QualityCheck(
        label,
        bool(change < 0),
        f"Shares change over period: {change*100:+.2f}%",
        category="capital_allocation",
    )


def check_eps_grows_faster_than_net_income(income, balance, cash) -> QualityCheck:
    """EPS CAGR > NI CAGR — buybacks amplifying."""
    label = "EPS grows faster than net income (buybacks amplify)"
    eps = _get(income, "eps_diluted")
    ni = _get(income, "net_income")
    if eps is None or ni is None:
        return _na(label, "Missing data", category="capital_allocation")
    eps_cagr = cagr(eps, periods=5)
    ni_cagr = cagr(ni, periods=5)
    if not _both_finite(eps_cagr, ni_cagr):
        return _na(label, "CAGR not computable", category="capital_allocation")
    return QualityCheck(
        label,
        bool(eps_cagr > ni_cagr + 0.005),
        f"EPS 5Y CAGR {eps_cagr*100:+.1f}% vs NI 5Y CAGR {ni_cagr*100:+.1f}%",
        category="capital_allocation",
    )


def check_eps_grows_faster_than_revenue(income, balance, cash) -> QualityCheck:
    """EPS > Revenue growth — operating leverage + buybacks combined."""
    label = "EPS grows faster than revenue"
    eps = _get(income, "eps_diluted")
    rev = _get(income, "revenue")
    if eps is None or rev is None:
        return _na(label, "Missing data", category="profitability")
    eps_cagr = cagr(eps, periods=5)
    rev_cagr = cagr(rev, periods=5)
    if not _both_finite(eps_cagr, rev_cagr):
        return _na(label, "CAGR not computable", category="profitability")
    return QualityCheck(
        label,
        bool(eps_cagr > rev_cagr),
        f"EPS 5Y CAGR {eps_cagr*100:+.1f}% vs Revenue 5Y CAGR {rev_cagr*100:+.1f}%",
        category="profitability",
    )


def check_fcf_grows_faster_than_ocf(income, balance, cash) -> QualityCheck:
    """FCF outpaces OCF — capex discipline."""
    label = "FCF grows faster than OCF (capex discipline)"
    fcf = free_cash_flow(cash)
    ocf = _get(cash, "ocf")
    if fcf is None or ocf is None:
        return _na(label, "Missing data", category="capital_allocation")
    fcf_cagr = cagr(fcf, periods=5)
    ocf_cagr = cagr(ocf, periods=5)
    if not _both_finite(fcf_cagr, ocf_cagr):
        return _na(label, "CAGR not computable", category="capital_allocation")
    return QualityCheck(
        label,
        bool(fcf_cagr > ocf_cagr),
        f"FCF 5Y CAGR {fcf_cagr*100:+.1f}% vs OCF 5Y CAGR {ocf_cagr*100:+.1f}%",
        category="capital_allocation",
    )


def check_margins_expanding(income, balance, cash) -> QualityCheck:
    """Net margin trend is positive over the last 5 years."""
    label = "Net margin is expanding"
    rev = _get(income, "revenue")
    ni = _get(income, "net_income")
    if rev is None or ni is None:
        return _na(label, "Missing data", category="profitability")
    margin = (ni / rev.replace(0, np.nan)).dropna().tail(5)
    if len(margin) < 3:
        return _na(label, "Need 3+ years", category="profitability")
    x = np.arange(len(margin))
    slope = float(np.polyfit(x, margin.values, 1)[0])
    return QualityCheck(
        label,
        bool(slope > 0.001),            # ≥10bp / year improvement
        f"Net margin slope: {slope*100:+.2f}pp/year over {len(margin)} years",
        category="profitability",
    )


def check_roe_increasing(income, balance, cash) -> QualityCheck:
    """ROE trend is positive."""
    label = "ROE is increasing"
    ni = _get(income, "net_income")
    eq = _get(balance, "total_equity")
    if ni is None or eq is None:
        return _na(label, "Missing data", category="profitability")
    roe = (ni / eq.replace(0, np.nan)).dropna().tail(5)
    if len(roe) < 3:
        return _na(label, "Need 3+ years", category="profitability")
    x = np.arange(len(roe))
    slope = float(np.polyfit(x, roe.values, 1)[0])
    return QualityCheck(
        label,
        bool(slope > 0.005),
        f"ROE slope: {slope*100:+.2f}pp/year — last value {roe.iloc[-1]*100:.1f}%",
        category="profitability",
    )


def check_no_dilution(income, balance, cash) -> QualityCheck:
    """Annual share dilution ≤ 1% (looser bar than buybacks-exceed-issuance)."""
    label = "No significant share dilution"
    shares = _get(income, "weighted_avg_shares")
    if shares is None or len(shares.dropna()) < 3:
        return _na(label, "Missing share-count", category="capital_allocation")
    s = shares.dropna()
    n = max(len(s) - 1, 1)
    annual_change = (s.iloc[-1] / s.iloc[0]) ** (1.0 / n) - 1.0
    return QualityCheck(
        label,
        bool(annual_change <= 0.01),
        f"Annual share change: {annual_change*100:+.2f}%",
        category="capital_allocation",
    )


# ============================================================
# Registry + runner
# ============================================================
ALL_CHECKS: list[Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame], QualityCheck]] = [
    check_revenue_accelerating,
    check_op_income_outpaces_revenue,
    check_high_margin_business,
    check_buybacks_exceed_issuance,
    check_eps_grows_faster_than_net_income,
    check_eps_grows_faster_than_revenue,
    check_fcf_grows_faster_than_ocf,
    check_margins_expanding,
    check_roe_increasing,
    check_no_dilution,
]


def run_checklist(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> ChecklistResult:
    """Run every quality check and return aggregated result."""
    return ChecklistResult(
        checks=[fn(income, balance, cash) for fn in ALL_CHECKS],
    )
