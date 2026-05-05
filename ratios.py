"""
Cálculo de ratios financieros.

Por qué hay un resolver de alias:
yfinance no es consistente con los nombres de las cuentas entre tickers
ni entre versiones. Una empresa puede tener "Stockholders Equity" y otra
"Total Stockholder Equity". El resolver intenta cada alias hasta encontrar
la columna.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Optional

# Aliases ordenados por preferencia (primero el nombre canónico nuevo)
FIELD_ALIASES = {
    "revenue": ["Total Revenue", "Revenue", "TotalRevenue"],
    "cogs": ["Cost Of Revenue", "CostOfRevenue", "Cost Of Goods Sold"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": ["Operating Income", "OperatingIncome", "EBIT"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
        "NetIncome",
    ],
    "interest_expense": ["Interest Expense", "InterestExpense"],
    "tax": ["Tax Provision", "Income Tax Expense"],
    "total_assets": ["Total Assets", "TotalAssets"],
    "total_equity": [
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Common Stock Equity",
    ],
    "total_debt": ["Total Debt", "TotalDebt"],
    "long_term_debt": ["Long Term Debt", "LongTermDebt"],
    "short_term_debt": ["Current Debt", "Short Long Term Debt"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
    "cash_eq": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash",
    ],
    "ocf": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Total Cash From Operating Activities",
    ],
    "capex": ["Capital Expenditure", "CapitalExpenditure"],
    "depreciation": [
        "Depreciation And Amortization",
        "Depreciation",
        "Reconciled Depreciation",
    ],
}


def _get(df: pd.DataFrame, key: str) -> Optional[pd.Series]:
    """Resuelve una serie histórica probando los aliases en orden."""
    if df is None or df.empty:
        return None
    for alias in FIELD_ALIASES.get(key, [key]):
        if alias in df.columns:
            return df[alias].astype(float)
    return None


def calculate_ratios(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve un DataFrame con índice temporal ascendente y columnas =
    ratios. Si una cuenta no está disponible, simplemente omite la
    columna (no rompe).
    """
    revenue = _get(income, "revenue")
    gross = _get(income, "gross_profit")
    op_inc = _get(income, "operating_income")
    net_inc = _get(income, "net_income")

    # EBITDA: si no viene reportado, lo reconstruimos (Op Income + D&A)
    ebitda = _get(income, "ebitda")
    if ebitda is None:
        da = _get(cash, "depreciation")
        if op_inc is not None and da is not None:
            ebitda = op_inc + da

    total_assets = _get(balance, "total_assets")
    total_equity = _get(balance, "total_equity")
    total_debt = _get(balance, "total_debt")
    if total_debt is None:
        # Reconstruir: LT + ST debt
        ltd = _get(balance, "long_term_debt")
        std = _get(balance, "short_term_debt")
        if ltd is not None and std is not None:
            total_debt = ltd.add(std, fill_value=0)
        elif ltd is not None:
            total_debt = ltd

    cur_assets = _get(balance, "current_assets")
    cur_liab = _get(balance, "current_liabilities")

    # FCF = Operating Cash Flow + Capex (capex viene NEGATIVO en yfinance)
    ocf = _get(cash, "ocf")
    capex = _get(cash, "capex")
    fcf = (ocf + capex) if (ocf is not None and capex is not None) else None

    idx = revenue.index if revenue is not None else (
        income.index if not income.empty else pd.DatetimeIndex([])
    )
    out = pd.DataFrame(index=idx)

    if revenue is not None:
        out["Revenue"] = revenue
        out["Revenue Growth %"] = revenue.pct_change() * 100
    if gross is not None and revenue is not None:
        out["Gross Margin %"] = gross / revenue * 100
    if op_inc is not None and revenue is not None:
        out["Operating Margin %"] = op_inc / revenue * 100
    if ebitda is not None:
        out["EBITDA"] = ebitda
        if revenue is not None:
            out["EBITDA Margin %"] = ebitda / revenue * 100
    if net_inc is not None:
        out["Net Income"] = net_inc
        if revenue is not None:
            out["Net Margin %"] = net_inc / revenue * 100

    # Rentabilidad
    if net_inc is not None and total_equity is not None:
        out["ROE %"] = net_inc / total_equity * 100
    if net_inc is not None and total_assets is not None:
        out["ROA %"] = net_inc / total_assets * 100

    # Solvencia / liquidez
    if total_debt is not None and total_equity is not None:
        out["Debt/Equity"] = total_debt / total_equity
    if cur_assets is not None and cur_liab is not None:
        out["Current Ratio"] = cur_assets / cur_liab

    # Cash flow
    if fcf is not None:
        out["FCF"] = fcf
        if revenue is not None:
            out["FCF Margin %"] = fcf / revenue * 100

    return out.round(2)


def cagr(series: pd.Series) -> float:
    """
    CAGR robusto. Devuelve NaN si no se puede calcular
    (datos insuficientes o valor inicial <= 0).
    """
    s = series.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return float("nan")
    n = len(s) - 1
    return (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
