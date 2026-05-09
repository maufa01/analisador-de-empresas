"""
Forward valuation by 5 multiples × N years.

For each forecast year, apply the peer-median multiple to the target's
projected metric to get an implied price, then discount back to PV at
``discount_rate`` (default 12%).

This is a CROSS-CHECK to the DCF — not a replacement. The 5 multiples
(P/E, P/FCF, EV/EBITDA, P/S, P/B) often diverge by 50%+; that divergence
is itself the information. Don't average aggressively — the panel UI
shows all five plus the simple mean.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# Result dataclasses
# ============================================================
@dataclass
class MultipleValuation:
    """Result for a single (year, multiple) cell."""
    multiple_name: str           # "P/E" | "P/FCF" | "EV/EBITDA" | "P/S" | "P/B"
    multiple_value: float        # peer median (e.g. 25.5 for P/E of 25.5x)
    implied_price: Optional[float]
    metric_value: float          # the per-share metric (EPS, FCF/share, etc.)
    metric_label: str            # "EPS", "FCF/share", etc.


@dataclass
class YearValuation:
    year: int
    valuations: list             # list[MultipleValuation]
    average_price: float
    median_price: float
    pv_discounted: float
    cagr_to_current: Optional[float]


@dataclass
class MultiMultipleResult:
    target_ticker: str
    current_price: float
    discount_rate: float
    years_forward: list          # list[YearValuation]

    peer_pe_median: Optional[float]
    peer_pfcf_median: Optional[float]
    peer_ev_ebitda_median: Optional[float]
    peer_ps_median: Optional[float]
    peer_pb_median: Optional[float]

    grand_average_price: float
    grand_pv_average: float


# ============================================================
# Internals
# ============================================================
def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _peer_multiple_medians(peer_snapshots: list) -> dict[str, Optional[float]]:
    """Compute median P/E, P/FCF, EV/EBITDA, P/S, P/B from peers.

    Each PeerSnapshot must expose at least: market_cap, net_income,
    revenue, ebitda, book_value, enterprise_value (optional — falls
    back to market_cap when missing).
    """
    pes:        list[float] = []
    pfcfs:      list[float] = []
    ev_ebitdas: list[float] = []
    pss:        list[float] = []
    pbs:        list[float] = []

    for p in peer_snapshots:
        mcap = _safe(getattr(p, "market_cap", None))
        ni = _safe(getattr(p, "net_income", None))
        rev = _safe(getattr(p, "revenue", None))
        ebitda = _safe(getattr(p, "ebitda", None))
        bv = _safe(getattr(p, "book_value", None))
        ev = _safe(getattr(p, "enterprise_value", None)) or mcap
        fcf = _safe(getattr(p, "fcf", None)) or _safe(getattr(p, "free_cash_flow", None))

        if mcap and ni and ni > 0:
            pes.append(mcap / ni)
        if mcap and fcf and fcf > 0:
            pfcfs.append(mcap / fcf)
        if ev and ebitda and ebitda > 0:
            ev_ebitdas.append(ev / ebitda)
        if mcap and rev and rev > 0:
            pss.append(mcap / rev)
        if mcap and bv and bv > 0:
            pbs.append(mcap / bv)

    def _med(lst: list[float]) -> Optional[float]:
        return float(np.median(lst)) if lst else None

    return {
        "pe":        _med(pes),
        "pfcf":      _med(pfcfs),
        "ev_ebitda": _med(ev_ebitdas),
        "ps":        _med(pss),
        "pb":        _med(pbs),
    }


def _proj_value(row: pd.Series, key: str) -> float:
    """Pull a projected metric from a forecast row, default 0."""
    if row is None or key not in row:
        return 0.0
    v = row.get(key)
    f = _safe(v)
    return f if f is not None else 0.0


# ============================================================
# Public API
# ============================================================
def run_multi_multiple_valuation(
    *,
    target_ticker: str,
    current_price: float,
    forecast_result,                  # ForecastResult from financial_forecast
    peer_snapshots: list,
    shares_outstanding: float,
    discount_rate: float = 0.12,
    base_year: Optional[int] = None,
) -> MultiMultipleResult:
    """Apply peer-median multiples to forecast projections, year by year.

    ``base_year`` defaults to today's year — used to compute how many years
    into the future each forecast row sits.
    """
    medians = _peer_multiple_medians(peer_snapshots)

    income_proj = forecast_result.income_projected
    balance_proj = forecast_result.balance_projected
    cash_proj = forecast_result.cash_flow_projected

    if base_year is None:
        base_year = pd.Timestamp.now().year

    year_results: list[YearValuation] = []

    for idx in income_proj.index:
        year_int = idx.year if isinstance(idx, pd.Timestamp) else int(str(idx)[:4])
        years_forward = year_int - base_year
        if years_forward <= 0:
            continue

        inc_row = income_proj.loc[idx]
        bal_row = (balance_proj.loc[idx] if idx in balance_proj.index
                   else pd.Series(dtype=float))
        cf_row = (cash_proj.loc[idx] if idx in cash_proj.index
                  else pd.Series(dtype=float))

        ni = _proj_value(inc_row, "netIncome")
        rev = _proj_value(inc_row, "revenue")
        ebitda = _proj_value(inc_row, "ebitda")
        fcf = _proj_value(cf_row, "freeCashFlow")
        equity = _proj_value(bal_row, "totalStockholdersEquity")
        debt = _proj_value(bal_row, "totalDebt")
        cash_bal = _proj_value(bal_row, "cashAndCashEquivalents")

        sh = float(shares_outstanding) if shares_outstanding else 0.0
        eps = (ni / sh) if sh > 0 else 0.0
        fcf_per_share = (fcf / sh) if sh > 0 else 0.0
        bv_per_share = (equity / sh) if sh > 0 else 0.0
        sales_per_share = (rev / sh) if sh > 0 else 0.0

        valuations: list[MultipleValuation] = []

        # P/E
        pe = medians["pe"]
        valuations.append(MultipleValuation(
            multiple_name="P/E",
            multiple_value=pe or 0.0,
            implied_price=(eps * pe) if (pe and eps > 0) else None,
            metric_value=eps,
            metric_label="EPS",
        ))

        # P/FCF
        pfcf = medians["pfcf"]
        valuations.append(MultipleValuation(
            multiple_name="P/FCF",
            multiple_value=pfcf or 0.0,
            implied_price=(fcf_per_share * pfcf) if (pfcf and fcf_per_share > 0) else None,
            metric_value=fcf_per_share,
            metric_label="FCF/share",
        ))

        # EV/EBITDA — implied equity = (EBITDA × m) − debt + cash, then /shares
        ev_m = medians["ev_ebitda"]
        if ev_m and ebitda > 0 and sh > 0:
            implied_ev = ebitda * ev_m
            implied_equity = implied_ev - debt + cash_bal
            ev_ebitda_price = implied_equity / sh
        else:
            ev_ebitda_price = None
        valuations.append(MultipleValuation(
            multiple_name="EV/EBITDA",
            multiple_value=ev_m or 0.0,
            implied_price=ev_ebitda_price,
            metric_value=ebitda,
            metric_label="EBITDA",
        ))

        # P/S
        ps = medians["ps"]
        valuations.append(MultipleValuation(
            multiple_name="P/S",
            multiple_value=ps or 0.0,
            implied_price=(sales_per_share * ps) if (ps and sales_per_share > 0) else None,
            metric_value=sales_per_share,
            metric_label="Sales/share",
        ))

        # P/B
        pb = medians["pb"]
        valuations.append(MultipleValuation(
            multiple_name="P/B",
            multiple_value=pb or 0.0,
            implied_price=(bv_per_share * pb) if (pb and bv_per_share > 0) else None,
            metric_value=bv_per_share,
            metric_label="BV/share",
        ))

        valid_prices = [v.implied_price for v in valuations
                        if v.implied_price and v.implied_price > 0]
        if not valid_prices:
            avg_price = median_price = pv = 0.0
            cagr: Optional[float] = None
        else:
            avg_price = float(np.mean(valid_prices))
            median_price = float(np.median(valid_prices))
            pv = avg_price / ((1.0 + discount_rate) ** years_forward)
            if current_price > 0:
                try:
                    cagr = (avg_price / current_price) ** (1.0 / years_forward) - 1.0
                except (ValueError, ZeroDivisionError):
                    cagr = None
            else:
                cagr = None

        year_results.append(YearValuation(
            year=year_int,
            valuations=valuations,
            average_price=avg_price,
            median_price=median_price,
            pv_discounted=pv,
            cagr_to_current=cagr,
        ))

    all_avgs = [yr.average_price for yr in year_results if yr.average_price > 0]
    all_pvs = [yr.pv_discounted for yr in year_results if yr.pv_discounted > 0]
    grand_avg = float(np.mean(all_avgs)) if all_avgs else 0.0
    grand_pv = float(np.mean(all_pvs)) if all_pvs else 0.0

    return MultiMultipleResult(
        target_ticker=target_ticker,
        current_price=float(current_price or 0.0),
        discount_rate=float(discount_rate),
        years_forward=year_results,
        peer_pe_median=medians["pe"],
        peer_pfcf_median=medians["pfcf"],
        peer_ev_ebitda_median=medians["ev_ebitda"],
        peer_ps_median=medians["ps"],
        peer_pb_median=medians["pb"],
        grand_average_price=grand_avg,
        grand_pv_average=grand_pv,
    )
