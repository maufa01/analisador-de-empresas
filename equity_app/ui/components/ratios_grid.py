"""
Ratios tab content — six render functions, one per sub-tab.

Each function takes the calculated ratios DataFrame + the company's
financials + the sector's industry averages, and renders a 3-column
grid of ``render_ratio_card`` calls.

Sparkline data for each card is pulled from the ratios DataFrame's
historical column when present, falling back to a derived series.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import streamlit as st

from analysis.ratios import _get, calculate_ratios, free_cash_flow
from data.company_profiles import get_industry_averages
from ui.components.ratio_card import render_ratio_card


# ============================================================
# Helpers
# ============================================================
def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _last(s: Optional[pd.Series]) -> Optional[float]:
    if s is None:
        return None
    clean = s.dropna()
    return float(clean.iloc[-1]) if not clean.empty else None


def _avg(s: Optional[pd.Series]) -> Optional[float]:
    if s is None:
        return None
    clean = s.dropna()
    return float(clean.mean()) if not clean.empty else None


def _series_history(s: Optional[pd.Series]) -> list[float]:
    if s is None:
        return []
    return [float(v) for v in s.dropna().tolist()]


def _safe_div(a, b) -> Optional[float]:
    a, b = _safe(a), _safe(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


# ============================================================
# Sub-tab 1 — Profitability (9 cards)
# ============================================================
def render_profitability(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
) -> None:
    ind = get_industry_averages(sector)

    cards = [
        ("Gross margin",      "Gross Margin %",      "gross_margin"),
        ("Operating margin",  "Operating Margin %",  "operating_margin"),
        ("Net margin",        "Net Margin %",        "net_margin"),
        ("EBITDA margin",     "EBITDA Margin %",     "ebitda_margin"),
        ("FCF margin",        "FCF Margin %",        "fcf_margin"),
        ("ROE",               "ROE %",               "roe"),
        ("ROA",               "ROA %",               "roa"),
        ("ROIC",              "ROIC %",              "roic"),
        ("Cash conversion",   "Cash Conversion",     None),  # already a ratio, not %
    ]

    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, (label, ratio_col, ind_key) in zip(cols, cards[i:i + 3]):
            with col:
                series = ratios.get(ratio_col)
                kind = "ratio" if label == "Cash conversion" else "pct"
                render_ratio_card(
                    label=label,
                    value=_last(series),
                    avg_10y=_avg(series),
                    industry_avg=(ind.get(ind_key) if ind_key else None),
                    history=_series_history(series),
                    kind=kind, higher_better=True,
                )


# ============================================================
# Sub-tab 2 — Efficiency (Asset turnover + days metrics)
# ============================================================
def render_efficiency(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
) -> None:
    ind = get_industry_averages(sector)

    rev = _get(income, "revenue")
    cogs = _get(income, "cost_of_revenue")
    receivables = _get(balance, "receivables")
    inventory = _get(balance, "inventory")
    payables = _get(balance, "current_liabilities")  # proxy: AP often missing
    assets = _get(balance, "total_assets")
    rd = _get(income, "depreciation_inc")            # closest proxy (R&D often absent)
    sga = _get(income, "sga")

    # Asset turnover series
    asset_turn = ((rev / assets) if rev is not None and assets is not None else None)
    asset_turn_v = _safe_div(_last(rev), _last(assets))

    # Days metrics — simple approximations (annual ÷ 365)
    dso = (_safe_div(_last(receivables), _last(rev)) or 0) * 365 if (
        receivables is not None and rev is not None) else None
    dio = (_safe_div(_last(inventory), _last(cogs)) or 0) * 365 if (
        inventory is not None and cogs is not None) else None
    dpo = (_safe_div(_last(payables), _last(cogs)) or 0) * 365 if (
        payables is not None and cogs is not None) else None
    ccc = (dso or 0) + (dio or 0) - (dpo or 0) if all(
        v is not None for v in (dso, dio, dpo)) else None

    sga_pct = _safe_div(_last(sga), _last(rev))
    sga_pct = sga_pct * 100 if sga_pct is not None else None
    rd_pct = _safe_div(_last(rd), _last(rev))
    rd_pct = rd_pct * 100 if rd_pct is not None else None

    cards = [
        {"label": "Asset turnover", "value": asset_turn_v,
         "history": _series_history(asset_turn), "kind": "ratio",
         "industry_avg": ind.get("asset_turnover"), "higher_better": True},
        {"label": "Days sales outstanding", "value": dso, "history": [],
         "kind": "days", "industry_avg": None, "higher_better": False},
        {"label": "Days inventory outstanding", "value": dio, "history": [],
         "kind": "days", "industry_avg": None, "higher_better": False},
        {"label": "Days payables outstanding", "value": dpo, "history": [],
         "kind": "days", "industry_avg": None, "higher_better": True},
        {"label": "Cash conversion cycle", "value": ccc, "history": [],
         "kind": "days", "industry_avg": None, "higher_better": False},
        {"label": "SG&A / Revenue", "value": sga_pct, "history": [],
         "kind": "pct", "industry_avg": None, "higher_better": False},
        {"label": "D&A / Revenue", "value": rd_pct, "history": [],
         "kind": "pct", "industry_avg": None, "higher_better": False},
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, c in zip(cols, cards[i:i + 3]):
            with col:
                render_ratio_card(**c)


# ============================================================
# Sub-tab 3 — Liquidity
# ============================================================
def render_liquidity(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
) -> None:
    ind = get_industry_averages(sector)

    ca = _get(balance, "current_assets")
    cl = _get(balance, "current_liabilities")
    inv = _get(balance, "inventory")
    cash_eq = _get(balance, "cash_eq")
    ocf = _get(cash, "ocf")

    current_ratio = (ca / cl) if (ca is not None and cl is not None) else None
    quick_ratio = ((ca - inv) / cl) if (ca is not None and inv is not None
                                        and cl is not None) else None
    cash_ratio = (cash_eq / cl) if (cash_eq is not None and cl is not None) else None

    cards = [
        {"label": "Current ratio", "value": _last(current_ratio),
         "history": _series_history(current_ratio), "kind": "ratio",
         "avg_10y": _avg(current_ratio),
         "industry_avg": ind.get("current_ratio"), "higher_better": True},
        {"label": "Quick ratio", "value": _last(quick_ratio),
         "history": _series_history(quick_ratio), "kind": "ratio",
         "avg_10y": _avg(quick_ratio),
         "industry_avg": ind.get("quick_ratio"), "higher_better": True},
        {"label": "Cash ratio", "value": _last(cash_ratio),
         "history": _series_history(cash_ratio), "kind": "ratio",
         "avg_10y": _avg(cash_ratio),
         "industry_avg": ind.get("cash_ratio"), "higher_better": True},
        {"label": "Working capital",
         "value": (_last(ca) or 0) - (_last(cl) or 0)
                  if (_last(ca) is not None and _last(cl) is not None) else None,
         "history": [], "kind": "currency_short", "higher_better": True},
        {"label": "Cash & equivalents", "value": _last(cash_eq),
         "history": _series_history(cash_eq), "kind": "currency_short",
         "higher_better": True},
        {"label": "OCF / current liabilities",
         "value": _safe_div(_last(ocf), _last(cl)),
         "history": [], "kind": "ratio", "higher_better": True},
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, c in zip(cols, cards[i:i + 3]):
            with col:
                render_ratio_card(**c)


# ============================================================
# Sub-tab 4 — Solvency / leverage
# ============================================================
def render_solvency(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
) -> None:
    ind = get_industry_averages(sector)

    debt = _get(balance, "total_debt")
    equity = _get(balance, "total_equity")
    assets = _get(balance, "total_assets")
    ebitda = _get(income, "ebitda")
    ebit = _get(income, "operating_income")
    interest = _get(income, "interest_expense")
    cash_eq = _get(balance, "cash_eq")

    de = (debt / equity) if (debt is not None and equity is not None) else None
    de_ebitda = (debt / ebitda) if (debt is not None and ebitda is not None) else None
    net_debt = (debt - cash_eq) if (debt is not None and cash_eq is not None) else None
    nd_ebitda = (net_debt / ebitda) if (net_debt is not None and ebitda is not None) else None
    d_assets = (debt / assets) if (debt is not None and assets is not None) else None
    eq_mult = (assets / equity) if (assets is not None and equity is not None) else None
    int_cov = (ebit / interest) if (ebit is not None and interest is not None) else None

    cards = [
        {"label": "Debt / equity", "value": _last(de),
         "history": _series_history(de), "kind": "ratio",
         "avg_10y": _avg(de),
         "industry_avg": ind.get("debt_to_equity"), "higher_better": False},
        {"label": "Debt / EBITDA", "value": _last(de_ebitda),
         "history": _series_history(de_ebitda), "kind": "ratio",
         "avg_10y": _avg(de_ebitda),
         "industry_avg": ind.get("debt_to_ebitda"), "higher_better": False},
        {"label": "Net debt / EBITDA", "value": _last(nd_ebitda),
         "history": _series_history(nd_ebitda), "kind": "ratio",
         "avg_10y": _avg(nd_ebitda), "higher_better": False},
        {"label": "Debt / assets", "value": _last(d_assets),
         "history": _series_history(d_assets), "kind": "ratio",
         "avg_10y": _avg(d_assets), "higher_better": False},
        {"label": "Equity multiplier", "value": _last(eq_mult),
         "history": _series_history(eq_mult), "kind": "ratio",
         "avg_10y": _avg(eq_mult), "higher_better": False},
        {"label": "Interest coverage", "value": _last(int_cov),
         "history": _series_history(int_cov), "kind": "multiple",
         "avg_10y": _avg(int_cov),
         "industry_avg": ind.get("interest_coverage"), "higher_better": True},
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, c in zip(cols, cards[i:i + 3]):
            with col:
                render_ratio_card(**c)


# ============================================================
# Sub-tab 5 — Per-share metrics
# ============================================================
def render_per_share(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
) -> None:
    eps = _get(income, "eps")
    eps_d = _get(income, "eps_diluted")
    shares = _get(income, "weighted_avg_shares")
    rev = _get(income, "revenue")
    fcf = free_cash_flow(cash)
    bv = _get(balance, "total_equity")
    cash_eq = _get(balance, "cash_eq")
    div = _get(cash, "dividends_paid")

    last_shares = _last(shares)

    bvps = (bv / shares) if (bv is not None and shares is not None) else None
    cps = (cash_eq / shares) if (cash_eq is not None and shares is not None) else None
    rps = (rev / shares) if (rev is not None and shares is not None) else None
    fcfps = (fcf / shares) if (fcf is not None and shares is not None) else None
    dps = (div.abs() / shares) if (div is not None and shares is not None) else None

    cards = [
        {"label": "EPS (basic)", "value": _last(eps),
         "history": _series_history(eps), "kind": "ratio",
         "avg_10y": _avg(eps), "higher_better": True},
        {"label": "EPS (diluted)", "value": _last(eps_d),
         "history": _series_history(eps_d), "kind": "ratio",
         "avg_10y": _avg(eps_d), "higher_better": True},
        {"label": "Book value / share", "value": _last(bvps),
         "history": _series_history(bvps), "kind": "ratio",
         "avg_10y": _avg(bvps), "higher_better": True},
        {"label": "Cash / share", "value": _last(cps),
         "history": _series_history(cps), "kind": "ratio",
         "avg_10y": _avg(cps), "higher_better": True},
        {"label": "Revenue / share", "value": _last(rps),
         "history": _series_history(rps), "kind": "ratio",
         "avg_10y": _avg(rps), "higher_better": True},
        {"label": "FCF / share", "value": _last(fcfps),
         "history": _series_history(fcfps), "kind": "ratio",
         "avg_10y": _avg(fcfps), "higher_better": True},
        {"label": "Dividend / share", "value": _last(dps),
         "history": _series_history(dps), "kind": "ratio",
         "avg_10y": _avg(dps), "higher_better": True},
        {"label": "Shares outstanding", "value": last_shares,
         "history": _series_history(shares), "kind": "currency_short",
         "higher_better": False},
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, c in zip(cols, cards[i:i + 3]):
            with col:
                render_ratio_card(**c)


# ============================================================
# Sub-tab 6 — Valuation multiples
#
# Most of these need a current price. We accept it as a kwarg and
# compute the surviving multiples; the rest render as "—".
# ============================================================
def render_valuation_multiples(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    ratios: pd.DataFrame, sector: Optional[str],
    current_price: Optional[float], market_cap: Optional[float],
    enterprise_value: Optional[float],
) -> None:
    ind = get_industry_averages(sector)

    rev = _last(_get(income, "revenue"))
    ni = _last(_get(income, "net_income"))
    ebitda = _last(_get(income, "ebitda"))
    fcf = _last(free_cash_flow(cash))
    eps_d = _last(_get(income, "eps_diluted"))
    bv = _last(_get(balance, "total_equity"))
    div_total = _last(_get(cash, "dividends_paid"))
    if div_total is not None:
        div_total = abs(div_total)

    pe = (current_price / eps_d) if (current_price and eps_d and eps_d > 0) else None
    pb = (market_cap / bv) if (market_cap and bv and bv > 0) else None
    ps = (market_cap / rev) if (market_cap and rev and rev > 0) else None
    p_fcf = (market_cap / fcf) if (market_cap and fcf and fcf > 0) else None
    ev_ebitda = (enterprise_value / ebitda) if (enterprise_value and ebitda
                                                and ebitda > 0) else None
    ev_sales = (enterprise_value / rev) if (enterprise_value and rev and rev > 0) else None
    ev_fcf = (enterprise_value / fcf) if (enterprise_value and fcf and fcf > 0) else None
    div_yield = (div_total / market_cap * 100) if (
        div_total and market_cap and market_cap > 0) else None
    fcf_yield = (fcf / market_cap * 100) if (
        fcf and market_cap and market_cap > 0) else None
    earnings_yield = (1.0 / pe * 100) if pe else None

    cards = [
        {"label": "P/E (TTM)", "value": pe, "history": [], "kind": "multiple",
         "industry_avg": ind.get("pe_ratio"), "higher_better": False},
        {"label": "P/B", "value": pb, "history": [], "kind": "multiple",
         "industry_avg": ind.get("pb_ratio"), "higher_better": False},
        {"label": "P/S", "value": ps, "history": [], "kind": "multiple",
         "industry_avg": ind.get("ps_ratio"), "higher_better": False},
        {"label": "P/FCF", "value": p_fcf, "history": [], "kind": "multiple",
         "higher_better": False},
        {"label": "EV/EBITDA", "value": ev_ebitda, "history": [],
         "kind": "multiple",
         "industry_avg": ind.get("ev_ebitda"), "higher_better": False},
        {"label": "EV/Sales", "value": ev_sales, "history": [],
         "kind": "multiple", "higher_better": False},
        {"label": "EV/FCF", "value": ev_fcf, "history": [],
         "kind": "multiple", "higher_better": False},
        {"label": "Dividend yield", "value": div_yield, "history": [],
         "kind": "pct", "higher_better": True},
        {"label": "FCF yield", "value": fcf_yield, "history": [],
         "kind": "pct", "higher_better": True},
        {"label": "Earnings yield", "value": earnings_yield, "history": [],
         "kind": "pct", "higher_better": True},
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3, gap="small")
        for col, c in zip(cols, cards[i:i + 3]):
            with col:
                render_ratio_card(**c)


# ============================================================
# Top-level dispatcher
# ============================================================
def render_ratios_grid(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    ratios: pd.DataFrame,
    sector: Optional[str],
    current_price: Optional[float] = None,
    market_cap: Optional[float] = None,
    enterprise_value: Optional[float] = None,
) -> None:
    """Pills + per-section grid. Caller embeds inside a tab."""
    sub = st.radio(
        "ratios_subtab",
        options=["Profitability", "Efficiency", "Liquidity",
                 "Solvency", "Per-share", "Valuation"],
        index=0, horizontal=True, label_visibility="collapsed",
        key="ratios_subtab_radio",
    )

    common = dict(income=income, balance=balance, cash=cash,
                  ratios=ratios, sector=sector)

    if sub == "Profitability":
        render_profitability(**common)
    elif sub == "Efficiency":
        render_efficiency(**common)
    elif sub == "Liquidity":
        render_liquidity(**common)
    elif sub == "Solvency":
        render_solvency(**common)
    elif sub == "Per-share":
        render_per_share(**common)
    elif sub == "Valuation":
        render_valuation_multiples(
            **common, current_price=current_price,
            market_cap=market_cap, enterprise_value=enterprise_value,
        )
