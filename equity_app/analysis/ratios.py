"""
Standard + adjusted financial ratios.

Operates primarily on FMP's DataFrame shape (camelCase), with alias
fallback for yfinance / Finviz / generic shapes. All inputs are expected
to be indexed by fiscal-period-end (ascending), one row per period.

Adjustments that matter for accuracy:

- **FCF adjusted for SBC.** Standard FCF treats stock-based compensation
  as non-cash, but SBC is economically dilutive. For tech where SBC is
  routinely 5–15% of revenue, ``fcf_adj = OCF + capex - SBC`` is the
  honest measure.

- **ROIC vs WACC.** ROIC = NOPAT / Invested Capital is the single
  cleanest test of whether incremental capital creates value.

- **Cash conversion.** FCF / Net Income < 0.7 sustained signals that
  earnings are not turning into cash — common precursor to writedowns.

The module never raises on missing fields; it omits the affected ratio
column. Downstream code MUST tolerate sparse columns.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# Field aliases — first match wins
# ============================================================
ALIASES: dict[str, list[str]] = {
    # ---- Income statement ----
    "revenue": ["revenue", "totalRevenue", "Total Revenue", "Revenue"],
    "cost_of_revenue": ["costOfRevenue", "Cost Of Revenue", "Cost Of Goods Sold"],
    "gross_profit": ["grossProfit", "Gross Profit"],
    "operating_income": ["operatingIncome", "Operating Income", "EBIT"],
    "ebit": ["ebit", "operatingIncome", "Operating Income", "EBIT"],
    "ebitda": ["ebitda", "EBITDA", "Normalized EBITDA"],
    "net_income": ["netIncome", "Net Income", "Net Income Common Stockholders"],
    "interest_expense": ["interestExpense", "Interest Expense"],
    "income_tax": ["incomeTaxExpense", "Tax Provision", "Income Tax Expense"],
    "sga": [
        "sellingGeneralAndAdministrativeExpenses",
        "Selling General And Administrative",
    ],
    "depreciation_inc": ["depreciationAndAmortization"],
    "eps": ["eps", "epsdiluted"],
    "eps_diluted": ["epsdiluted", "eps"],
    "weighted_avg_shares": [
        "weightedAverageShsOut", "weightedAverageShsOutDil", "Diluted Average Shares",
    ],

    # ---- Balance sheet ----
    "total_assets": ["totalAssets", "Total Assets"],
    "total_liabilities": ["totalLiabilities", "Total Liabilities"],
    "total_equity": [
        "totalStockholdersEquity", "totalEquity",
        "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity",
    ],
    "total_debt": ["totalDebt", "Total Debt"],
    "long_term_debt": ["longTermDebt", "Long Term Debt"],
    "short_term_debt": ["shortTermDebt", "Current Debt", "Short Long Term Debt"],
    "current_assets": ["totalCurrentAssets", "Current Assets", "Total Current Assets"],
    "current_liabilities": [
        "totalCurrentLiabilities", "Current Liabilities", "Total Current Liabilities",
    ],
    "cash_eq": [
        "cashAndCashEquivalents", "cashAndShortTermInvestments",
        "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
    ],
    "ppe": ["propertyPlantEquipmentNet", "Property Plant Equipment Net"],
    "receivables": ["netReceivables", "Net Receivables"],
    "inventory": ["inventory", "Inventory"],
    "goodwill": ["goodwill", "Goodwill"],
    "intangibles": [
        "intangibleAssets", "goodwillAndIntangibleAssets", "Intangible Assets",
    ],
    "common_shares_outstanding": [
        "commonStockSharesOutstanding", "commonStock", "Share Issued",
    ],

    # ---- Cash flow ----
    "ocf": [
        "operatingCashFlow", "netCashProvidedByOperatingActivities",
        "Operating Cash Flow", "Total Cash From Operating Activities",
    ],
    "capex": [
        "capitalExpenditure", "investmentsInPropertyPlantAndEquipment",
        "Capital Expenditure",
    ],
    "fcf": ["freeCashFlow"],
    "sbc": ["stockBasedCompensation", "Stock Based Compensation"],
    "depreciation_cf": [
        "depreciationAndAmortization", "Depreciation And Amortization",
        "Reconciled Depreciation",
    ],
    "dividends_paid": ["dividendsPaid"],
    "buybacks": [
        "commonStockRepurchased", "stockRepurchase", "Repurchase Of Capital Stock",
    ],
    "shares_change": ["commonStockIssued"],
}


# ============================================================
# Internal helpers
# ============================================================
def _get(df: pd.DataFrame | None, key: str) -> Optional[pd.Series]:
    """Resolve a series via the alias chain. Returns None when unknown."""
    if df is None or df.empty:
        return None
    for alias in ALIASES.get(key, [key]):
        if alias in df.columns:
            try:
                return df[alias].astype(float)
            except (ValueError, TypeError):
                continue
    return None


def _safe_div(a: pd.Series | float | None, b: pd.Series | float | None):
    """Element-wise safe division; returns None when either is None."""
    if a is None or b is None:
        return None
    return a / b


def _pct(s: pd.Series | None) -> Optional[pd.Series]:
    return None if s is None else s * 100


# ============================================================
# Growth — CAGR / YoY
# ============================================================
def cagr(series: pd.Series, periods: int | None = None) -> float:
    """
    CAGR over N periods (default: full series).

    Returns NaN if the start value is non-positive or there are fewer
    than 2 observations after dropping NaN.
    """
    s = series.dropna() if series is not None else pd.Series(dtype=float)
    if periods is not None:
        s = s.tail(periods + 1)        # need N+1 points for N intervals
    if len(s) < 2:
        return float("nan")
    if s.iloc[0] <= 0:
        return float("nan")
    n = len(s) - 1
    return float((s.iloc[-1] / s.iloc[0]) ** (1.0 / n) - 1.0)


def yoy_growth(series: pd.Series) -> pd.Series:
    """Year-over-year change as a fraction (decimal)."""
    if series is None or series.empty:
        return pd.Series(dtype=float)
    return series.pct_change()


# ============================================================
# FCF & capex
# ============================================================
def free_cash_flow(cash: pd.DataFrame) -> Optional[pd.Series]:
    """FCF = OCF + capex (capex is negative). Returns None if either missing."""
    fcf_direct = _get(cash, "fcf")
    if fcf_direct is not None and not fcf_direct.dropna().empty:
        return fcf_direct
    ocf = _get(cash, "ocf")
    capex = _get(cash, "capex")
    if ocf is None or capex is None:
        return None
    return ocf + capex


def adjusted_fcf(cash: pd.DataFrame) -> Optional[pd.Series]:
    """
    FCF − stock-based compensation. Conservative cash-earnings measure.

    Returns regular FCF if SBC is not reported (treats SBC=0 as best
    available approximation; the column name itself in the output makes
    the ambiguity explicit).
    """
    fcf = free_cash_flow(cash)
    if fcf is None:
        return None
    sbc = _get(cash, "sbc")
    if sbc is None:
        return fcf
    return fcf - sbc.fillna(0.0)


def maintenance_capex_estimate(cash: pd.DataFrame, years: int = 5) -> Optional[float]:
    """
    Crude maintenance capex estimate: average D&A over last N years.

    Better than nothing when the 10-K doesn't break out maintenance vs
    growth capex. For more rigorous splits, use Bruce Greenwald's method
    (capex-growth = capex × revenue_growth × PPE/sales).
    """
    da = _get(cash, "depreciation_cf")
    if da is None:
        return None
    s = da.dropna().tail(years)
    return float(s.mean()) if not s.empty else None


# ============================================================
# Working capital
# ============================================================
def working_capital(balance: pd.DataFrame) -> Optional[pd.Series]:
    ca = _get(balance, "current_assets")
    cl = _get(balance, "current_liabilities")
    if ca is None or cl is None:
        return None
    return ca - cl


def change_in_wc(balance: pd.DataFrame) -> Optional[pd.Series]:
    wc = working_capital(balance)
    return None if wc is None else wc.diff()


# ============================================================
# Profitability
# ============================================================
def roe(income: pd.DataFrame, balance: pd.DataFrame) -> Optional[pd.Series]:
    ni = _get(income, "net_income")
    eq = _get(balance, "total_equity")
    return _safe_div(ni, eq)


def roa(income: pd.DataFrame, balance: pd.DataFrame) -> Optional[pd.Series]:
    ni = _get(income, "net_income")
    ta = _get(balance, "total_assets")
    return _safe_div(ni, ta)


def roic(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    *,
    tax_rate: float | None = None,
) -> Optional[pd.Series]:
    """
    ROIC = NOPAT / Invested Capital.

    NOPAT = EBIT × (1 − effective tax rate).
    Invested Capital = Total Equity + Total Debt − Cash.
    """
    ebit = _get(income, "ebit")
    if ebit is None:
        return None
    if tax_rate is None:
        tax_rate = effective_tax_rate(income)
    nopat = ebit * (1.0 - tax_rate)
    eq = _get(balance, "total_equity")
    debt = _get(balance, "total_debt")
    if debt is None:
        # reconstruct from LT + ST debt
        ltd = _get(balance, "long_term_debt")
        std = _get(balance, "short_term_debt")
        if ltd is not None:
            debt = ltd.add(std, fill_value=0.0) if std is not None else ltd
    cash = _get(balance, "cash_eq")
    if eq is None or debt is None:
        return None
    invested = eq + debt - (cash if cash is not None else 0.0)
    return _safe_div(nopat, invested)


def effective_tax_rate(income: pd.DataFrame, periods: int | None = 3) -> float:
    """3-year average effective tax rate; falls back to 0.25 if unknown."""
    tax = _get(income, "income_tax")
    pretax = _get(income, "ebit")
    if tax is None or pretax is None:
        return 0.25
    if periods:
        tax = tax.tail(periods)
        pretax = pretax.tail(periods)
    valid = (tax.notna()) & (pretax.notna()) & (pretax != 0)
    if not valid.any():
        return 0.25
    rate = float((tax[valid] / pretax[valid]).mean())
    # Sanity clamp — anything outside [0, 0.5] is almost surely a data glitch.
    if not np.isfinite(rate) or rate < 0:
        return 0.25
    return min(rate, 0.50)


# ============================================================
# Solvency / liquidity
# ============================================================
def debt_to_equity(balance: pd.DataFrame) -> Optional[pd.Series]:
    debt = _get(balance, "total_debt")
    eq = _get(balance, "total_equity")
    return _safe_div(debt, eq)


def debt_to_ebitda(income: pd.DataFrame, balance: pd.DataFrame) -> Optional[pd.Series]:
    debt = _get(balance, "total_debt")
    ebitda = _get(income, "ebitda")
    return _safe_div(debt, ebitda)


def net_debt_to_ebitda(
    income: pd.DataFrame, balance: pd.DataFrame
) -> Optional[pd.Series]:
    debt = _get(balance, "total_debt")
    cash = _get(balance, "cash_eq")
    ebitda = _get(income, "ebitda")
    if debt is None or ebitda is None:
        return None
    nd = debt - (cash if cash is not None else 0.0)
    return _safe_div(nd, ebitda)


def interest_coverage(income: pd.DataFrame) -> Optional[pd.Series]:
    """EBIT / Interest Expense (interest expense expected positive)."""
    ebit = _get(income, "ebit")
    ix = _get(income, "interest_expense")
    if ebit is None or ix is None:
        return None
    ix_abs = ix.abs().replace(0.0, np.nan)
    return ebit / ix_abs


def current_ratio(balance: pd.DataFrame) -> Optional[pd.Series]:
    return _safe_div(
        _get(balance, "current_assets"),
        _get(balance, "current_liabilities"),
    )


def quick_ratio(balance: pd.DataFrame) -> Optional[pd.Series]:
    ca = _get(balance, "current_assets")
    inv = _get(balance, "inventory")
    cl = _get(balance, "current_liabilities")
    if ca is None or cl is None:
        return None
    quick = ca - (inv if inv is not None else 0.0)
    return _safe_div(quick, cl)


# ============================================================
# Master aggregator
# ============================================================
def calculate_ratios(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    *,
    wacc: float | None = None,
) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by fiscal-period-end with ratio columns.

    Missing inputs degrade gracefully — affected columns are simply not
    emitted. Downstream code must check for column presence.
    """
    revenue = _get(income, "revenue")
    gross = _get(income, "gross_profit")
    op_inc = _get(income, "operating_income")
    net_inc = _get(income, "net_income")

    ebitda = _get(income, "ebitda")
    if ebitda is None:
        # Reconstruct: EBIT + D&A.
        # `_get` returns a pd.Series; using `or` triggers __bool__ which
        # raises 'truth value of a Series is ambiguous'. Pick explicitly
        # by None instead — cash flow first (more reliable D&A source),
        # then income statement.
        da = _get(cash, "depreciation_cf")
        if da is None:
            da = _get(income, "depreciation_inc")
        if op_inc is not None and da is not None:
            ebitda = op_inc + da

    idx = revenue.index if revenue is not None else (
        income.index if not income.empty else pd.DatetimeIndex([])
    )
    out = pd.DataFrame(index=idx)

    # ---- Top line + growth ----
    if revenue is not None:
        out["Revenue"] = revenue
        out["Revenue Growth %"] = _pct(yoy_growth(revenue))
    if net_inc is not None:
        out["Net Income"] = net_inc

    # ---- Margins ----
    if revenue is not None:
        if gross is not None:
            out["Gross Margin %"] = _pct(gross / revenue)
        if op_inc is not None:
            out["Operating Margin %"] = _pct(op_inc / revenue)
        if ebitda is not None:
            out["EBITDA"] = ebitda
            out["EBITDA Margin %"] = _pct(ebitda / revenue)
        if net_inc is not None:
            out["Net Margin %"] = _pct(net_inc / revenue)

    # ---- Cash flow ----
    fcf = free_cash_flow(cash)
    fcf_adj = adjusted_fcf(cash)
    if fcf is not None:
        out["FCF"] = fcf
        if revenue is not None:
            out["FCF Margin %"] = _pct(fcf / revenue)
    if fcf_adj is not None:
        out["FCF Adjusted (SBC)"] = fcf_adj
        if revenue is not None:
            out["FCF Adj Margin %"] = _pct(fcf_adj / revenue)
    if fcf is not None and net_inc is not None:
        out["Cash Conversion"] = fcf / net_inc.replace(0, np.nan)

    # ---- Returns ----
    s = roe(income, balance);   out["ROE %"] = _pct(s) if s is not None else None
    s = roa(income, balance);   out["ROA %"] = _pct(s) if s is not None else None
    s = roic(income, balance);  out["ROIC %"] = _pct(s) if s is not None else None
    if "ROIC %" in out.columns and wacc is not None:
        out["ROIC - WACC (pp)"] = out["ROIC %"] - (wacc * 100.0)

    # ---- Solvency ----
    s = debt_to_equity(balance);     out["Debt/Equity"] = s
    s = debt_to_ebitda(income, balance);   out["Debt/EBITDA"] = s
    s = net_debt_to_ebitda(income, balance); out["Net Debt/EBITDA"] = s
    s = interest_coverage(income);   out["Interest Coverage"] = s

    # ---- Liquidity ----
    s = current_ratio(balance);  out["Current Ratio"] = s
    s = quick_ratio(balance);    out["Quick Ratio"] = s

    # Drop columns that came back None (the simple assignment above
    # leaves them as None scalars, which we don't want).
    out = out.dropna(axis=1, how="all")
    return out.round(4)


# ============================================================
# Growth summary (3y / 5y / 10y CAGR)
# ============================================================
def growth_summary(income: pd.DataFrame, cash: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Returns {metric: {3y, 5y, 10y}} CAGR map."""
    out: dict[str, dict[str, float]] = {}
    rev = _get(income, "revenue")
    eps = _get(income, "eps")
    fcf = free_cash_flow(cash)
    for label, series in (("revenue", rev), ("eps", eps), ("fcf", fcf)):
        if series is None:
            continue
        out[label] = {
            "cagr_3y": cagr(series, periods=3),
            "cagr_5y": cagr(series, periods=5),
            "cagr_10y": cagr(series, periods=10),
        }
    return out
