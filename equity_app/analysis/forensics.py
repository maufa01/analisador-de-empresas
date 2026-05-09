"""
Forensic flags — pure-function rule set that flags specific
accounting / earnings-quality concerns.

Each rule is a pure ``(income, balance, cash) → Optional[ForensicFlag]``
function. ``run_all_checks`` runs them all and returns the list of
flags that fired (no flag returned = no issue).

Distinct from :mod:`analysis.quality_checklist`:
- quality_checklist is a yes/no Phil-Town style scoring of POSITIVES
  ("Are the margins expanding?")
- forensics is the inverse: rules that flag SUSPICIOUS PATTERNS
  ("Receivables grew 3x faster than revenue — channel stuffing risk")
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Literal, Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow


Severity = Literal["info", "warning", "critical"]


@dataclass
class ForensicFlag:
    label: str
    severity: Severity                # "info" | "warning" | "critical"
    detail: str                       # 1-line numeric justification
    category: str = "general"         # accruals | growth_quality | capital | etc.


# ============================================================
# Helpers
# ============================================================
def _last_n(s: pd.Series, n: int) -> pd.Series:
    return s.dropna().tail(n)


def _yoy_pct(s: pd.Series, periods: int = 1) -> Optional[float]:
    s = s.dropna()
    if len(s) < periods + 1 or s.iloc[-periods - 1] == 0:
        return None
    return float((s.iloc[-1] / s.iloc[-periods - 1]) - 1)


def _cagr(s: pd.Series, periods: int) -> Optional[float]:
    s = s.dropna()
    if len(s) < periods + 1 or s.iloc[-periods - 1] <= 0:
        return None
    return float((s.iloc[-1] / s.iloc[-periods - 1]) ** (1 / periods) - 1)


# ============================================================
# Individual rules
# ============================================================
def check_low_cash_conversion(income, balance, cash) -> Optional[ForensicFlag]:
    """FCF / NI sustained < 0.5 → 'paper earnings' that don't translate to cash."""
    ni = _get(income, "net_income")
    fcf = free_cash_flow(cash)
    if ni is None or fcf is None:
        return None
    common = ni.index.intersection(fcf.index)
    last3 = (fcf.loc[common] / ni.loc[common].replace(0, np.nan)).dropna().tail(3)
    if len(last3) < 3:
        return None
    avg = float(last3.mean())
    if avg < 0.5 and float(last3.max()) < 0.7:
        return ForensicFlag(
            label="Low cash conversion",
            severity="warning",
            detail=f"FCF/NI averaged {avg:.2f} over 3y (>0.7 in any year would clear this).",
            category="accruals",
        )
    return None


def check_receivables_outpace_revenue(income, balance, cash) -> Optional[ForensicFlag]:
    """AR growth > Revenue growth × 1.5 → channel stuffing risk."""
    rev = _get(income, "revenue")
    rec = _get(balance, "receivables")
    if rev is None or rec is None:
        return None
    rev_g = _yoy_pct(rev)
    rec_g = _yoy_pct(rec)
    if rev_g is None or rec_g is None:
        return None
    if rev_g <= 0 or rec_g <= 0:
        return None
    if rec_g > rev_g * 1.5 and (rec_g - rev_g) > 0.10:
        return ForensicFlag(
            label="Receivables outpacing revenue",
            severity="warning",
            detail=(f"AR YoY {rec_g*100:+.1f}% vs Revenue YoY "
                    f"{rev_g*100:+.1f}% — possible channel stuffing or "
                    "weakening customer credit."),
            category="accruals",
        )
    return None


def check_inventory_outpaces_revenue(income, balance, cash) -> Optional[ForensicFlag]:
    """Inventory growth >> revenue growth → demand softening."""
    rev = _get(income, "revenue")
    inv = _get(balance, "inventory")
    if rev is None or inv is None:
        return None
    rev_g = _yoy_pct(rev)
    inv_g = _yoy_pct(inv)
    if rev_g is None or inv_g is None:
        return None
    if rev_g <= 0:
        return None
    if inv_g > rev_g * 1.5 and (inv_g - rev_g) > 0.10:
        return ForensicFlag(
            label="Inventory outpacing revenue",
            severity="warning",
            detail=(f"Inventory YoY {inv_g*100:+.1f}% vs Revenue YoY "
                    f"{rev_g*100:+.1f}% — soft demand or sell-through "
                    "deterioration."),
            category="growth_quality",
        )
    return None


def check_goodwill_dominance(income, balance, cash) -> Optional[ForensicFlag]:
    """Goodwill > 50% of total assets → impairment risk."""
    gw = _get(balance, "goodwill")
    ta = _get(balance, "total_assets")
    if gw is None or ta is None:
        return None
    last_gw = gw.dropna()
    last_ta = ta.dropna()
    if last_gw.empty or last_ta.empty:
        return None
    pct = float(last_gw.iloc[-1]) / float(last_ta.iloc[-1])
    if pct > 0.50:
        return ForensicFlag(
            label="Goodwill-heavy balance sheet",
            severity="critical",
            detail=(f"Goodwill is {pct*100:.0f}% of total assets — "
                    "elevated impairment risk after acquisitions."),
            category="balance_sheet",
        )
    if pct > 0.30:
        return ForensicFlag(
            label="Goodwill elevated",
            severity="warning",
            detail=f"Goodwill {pct*100:.0f}% of total assets.",
            category="balance_sheet",
        )
    return None


def check_share_dilution(income, balance, cash) -> Optional[ForensicFlag]:
    """Share count growing >5% per year sustained → ongoing dilution."""
    shares = _get(income, "weighted_avg_shares")
    if shares is None or len(shares.dropna()) < 4:
        return None
    cagr_3y = _cagr(shares, periods=3)
    if cagr_3y is None:
        return None
    if cagr_3y > 0.05:
        return ForensicFlag(
            label="Sustained share dilution",
            severity="warning",
            detail=(f"Share count CAGR over 3y: +{cagr_3y*100:.1f}% — "
                    "SBC-heavy or capital raises eating value-per-share."),
            category="capital_allocation",
        )
    return None


def check_debt_jump(income, balance, cash) -> Optional[ForensicFlag]:
    """Debt YoY > 50% jump → leverage ramp; needs context."""
    debt = _get(balance, "total_debt")
    if debt is None:
        return None
    yoy = _yoy_pct(debt)
    if yoy is None:
        return None
    if yoy > 0.5:
        return ForensicFlag(
            label="Debt jumped sharply",
            severity="warning",
            detail=(f"Total debt YoY +{yoy*100:.1f}% — verify the use of "
                    "proceeds (M&A, buybacks, refinancing)."),
            category="capital_allocation",
        )
    return None


def check_negative_fcf_with_growth(income, balance, cash) -> Optional[ForensicFlag]:
    """Sustained negative FCF + revenue growing → growth-at-any-cost."""
    rev = _get(income, "revenue")
    fcf = free_cash_flow(cash)
    if rev is None or fcf is None:
        return None
    last_fcf = _last_n(fcf, 3)
    last_rev = _last_n(rev, 4)
    if len(last_fcf) < 3 or len(last_rev) < 2:
        return None
    if (last_fcf < 0).all():
        rev_growth = _yoy_pct(last_rev)
        if rev_growth and rev_growth > 0.10:
            return ForensicFlag(
                label="Negative FCF with growth",
                severity="warning",
                detail=(f"FCF was negative all 3 of the last 3 years while "
                        f"revenue grew {rev_growth*100:+.1f}% YoY — "
                        "growth-at-any-cost risk."),
                category="growth_quality",
            )
    return None


def check_eps_lags_net_income(income, balance, cash) -> Optional[ForensicFlag]:
    """EPS growth materially below NI growth → dilution eating EPS gains.
    Inverse of the positive 'EPS amplifies via buybacks' check."""
    ni = _get(income, "net_income")
    eps = _get(income, "eps_diluted")
    if ni is None or eps is None:
        return None
    ni_cagr = _cagr(ni, periods=5)
    eps_cagr = _cagr(eps, periods=5)
    if ni_cagr is None or eps_cagr is None:
        return None
    if ni_cagr > 0.03 and eps_cagr < ni_cagr - 0.03:
        return ForensicFlag(
            label="EPS lags net income",
            severity="info",
            detail=(f"NI 5Y CAGR {ni_cagr*100:+.1f}% vs EPS 5Y CAGR "
                    f"{eps_cagr*100:+.1f}% — share count dilution is "
                    "eating earnings-per-share gains."),
            category="capital_allocation",
        )
    return None


# ============================================================
# Registry + runner
# ============================================================
ALL_CHECKS: list[Callable] = [
    check_low_cash_conversion,
    check_receivables_outpace_revenue,
    check_inventory_outpaces_revenue,
    check_goodwill_dominance,
    check_share_dilution,
    check_debt_jump,
    check_negative_fcf_with_growth,
    check_eps_lags_net_income,
]


def run_all_checks(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> list[ForensicFlag]:
    """Run every forensic rule. Each rule returns either ``None`` (no
    issue) or a :class:`ForensicFlag`. The result is the concatenated
    list of fired flags — empty list when everything passes."""
    out: list[ForensicFlag] = []
    for fn in ALL_CHECKS:
        try:
            flag = fn(income, balance, cash)
        except Exception:
            continue
        if flag is not None:
            out.append(flag)
    return out
