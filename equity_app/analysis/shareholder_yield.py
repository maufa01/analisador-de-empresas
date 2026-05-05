"""
Shareholder yield = (dividends + net buybacks) / market cap.

Net buybacks = stock repurchased − stock issued. A negative shareholder
yield means the company is diluting net of returns — a structural drag
on per-share value that is invisible on the income statement.

Inputs are the same cash-flow dataframe the rest of the pipeline already
loads + the market cap that the page already has from its DEMO maps /
yfinance fast_info.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from analysis.ratios import _get


# ============================================================
# Result
# ============================================================
@dataclass
class ShareholderYield:
    available: bool
    flag: str                                  # green / yellow / red
    label: str                                 # EXCELLENT / STRONG / MODERATE / WEAK / DILUTING

    dividend_yield_pct: Optional[float] = None
    net_buyback_yield_pct: Optional[float] = None
    issuance_dilution_pct: Optional[float] = None
    total_yield_pct: Optional[float] = None
    avg_3y_yield_pct: Optional[float] = None

    annual_dividends: Optional[float] = None
    gross_buybacks: Optional[float] = None
    issuance: Optional[float] = None
    net_to_shareholders: Optional[float] = None
    market_cap: Optional[float] = None

    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    interpretation: str = ""
    note: str = ""


# ============================================================
# Helpers — extract per-period series in absolute, positive values
# ============================================================
def _abs_series(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    s = _get(df, key)
    if s is None:
        return None
    s = s.dropna()
    if s.empty:
        return None
    return s.abs()


def _positive_series(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    """Issuance is reported as a positive number when shares are sold; keep
    only positive values (negative entries are net repurchases)."""
    s = _get(df, key)
    if s is None:
        return None
    s = s.dropna()
    if s.empty:
        return None
    return s.where(s > 0, 0.0)


def _classify(total_yield_pct: float) -> tuple[str, str, str]:
    if total_yield_pct >= 8.0:
        return ("green", "EXCELLENT",
                "Aggressive capital return — premium capital allocation.")
    if total_yield_pct >= 5.0:
        return ("green", "STRONG",
                "Strong capital return to shareholders.")
    if total_yield_pct >= 2.0:
        return ("yellow", "MODERATE",
                "Modest shareholder return — typical for growth companies still reinvesting.")
    if total_yield_pct >= 0:
        return ("yellow", "WEAK",
                "Minimal capital return.")
    return ("red", "DILUTING",
            "Net dilution — issuance exceeds returns. Per-share value erodes.")


# ============================================================
# Public API
# ============================================================
def calculate_shareholder_yield(
    *, cash: pd.DataFrame, market_cap: Optional[float],
) -> ShareholderYield:
    if not market_cap or market_cap <= 0:
        return ShareholderYield(
            available=False, flag="unknown", label="N/A",
            note="Market cap unavailable — shareholder yield needs a denominator.",
        )

    div_s = _abs_series(cash, "dividends_paid")
    buy_s = _abs_series(cash, "buybacks")
    iss_s = _positive_series(cash, "shares_change")

    if all(s is None for s in (div_s, buy_s, iss_s)):
        return ShareholderYield(
            available=False, flag="unknown", label="N/A",
            note="Cash-flow statement does not expose dividends/buybacks/issuance.",
        )

    # Latest year — pick the most recent index that any series has
    common_idx = pd.Index([])
    for s in (div_s, buy_s, iss_s):
        if s is not None:
            common_idx = common_idx.union(s.index)
    if common_idx.empty:
        return ShareholderYield(
            available=False, flag="unknown", label="N/A",
            note="No usable dates in cash flow statement.",
        )

    latest = common_idx.max()
    div_latest = float(div_s.loc[latest]) if div_s is not None and latest in div_s.index else 0.0
    buy_latest = float(buy_s.loc[latest]) if buy_s is not None and latest in buy_s.index else 0.0
    iss_latest = float(iss_s.loc[latest]) if iss_s is not None and latest in iss_s.index else 0.0

    net_buy = buy_latest - iss_latest
    net_to_holders = div_latest + net_buy

    div_yield = (div_latest / market_cap) * 100
    buy_yield = (net_buy / market_cap) * 100
    iss_drag = (iss_latest / market_cap) * 100
    total_yield = (net_to_holders / market_cap) * 100

    flag, label, interp = _classify(total_yield)

    # 3y rolling average — use last 3 dates that exist in any series
    last3 = common_idx.sort_values()[-3:]
    history_rows = []
    avg_total = 0.0
    n_years = 0
    for d in last3:
        d_div = float(div_s.loc[d]) if div_s is not None and d in div_s.index else 0.0
        d_buy = float(buy_s.loc[d]) if buy_s is not None and d in buy_s.index else 0.0
        d_iss = float(iss_s.loc[d]) if iss_s is not None and d in iss_s.index else 0.0
        d_total = ((d_div + d_buy - d_iss) / market_cap) * 100
        avg_total += d_total
        n_years += 1
        history_rows.append({
            "date":          d,
            "dividends":     d_div,
            "buybacks":      d_buy,
            "issuance":      d_iss,
            "yield_pct":     d_total,
        })

    avg_3y = (avg_total / n_years) if n_years else None

    return ShareholderYield(
        available=True,
        flag=flag,
        label=label,
        dividend_yield_pct=float(div_yield),
        net_buyback_yield_pct=float(buy_yield),
        issuance_dilution_pct=float(iss_drag),
        total_yield_pct=float(total_yield),
        avg_3y_yield_pct=(float(avg_3y) if avg_3y is not None else None),
        annual_dividends=float(div_latest),
        gross_buybacks=float(buy_latest),
        issuance=float(iss_latest),
        net_to_shareholders=float(net_to_holders),
        market_cap=float(market_cap),
        history=pd.DataFrame(history_rows).set_index("date") if history_rows else pd.DataFrame(),
        interpretation=interp,
        note=("Issuance is whatever the cash flow statement labels as common-stock-issued "
              "with positive sign — net of repurchases reported on the same line."),
    )
