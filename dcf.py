"""
Modelo Discounted Cash Flow de dos etapas:
1) Proyección explícita de FCF a N años usando un growth rate
   (CAGR histórico por default, override manual disponible).
2) Terminal Value via modelo de Gordon: TV = FCF_n+1 / (WACC - g_terminal)

Equity Value = EV - Total Debt + Cash
Precio intrínseco = Equity Value / Shares Outstanding

Supuestos explícitos:
- Capex viene negativo en yfinance => FCF = OCF + Capex (sin abs)
- Net Debt = Total Debt - Cash & Equivalents
- WACC > g terminal (sino Gordon explota)
- Growth se capa entre [-5%, +20%] para evitar proyecciones absurdas
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from ratios import _get, cagr
from config import DCF_DEFAULTS


@dataclass
class DCFInputs:
    fcf_history: pd.Series
    shares_outstanding: float
    total_debt: float
    cash: float
    wacc: float
    terminal_growth: float
    projection_years: int = 5
    growth_rate: Optional[float] = None  # None => usa CAGR histórico


@dataclass
class DCFResult:
    enterprise_value: float
    equity_value: float
    intrinsic_per_share: float
    projected_fcf: pd.Series
    pv_fcf: pd.Series
    terminal_value: float
    pv_terminal: float
    growth_used: float
    inputs: DCFInputs


def calculate_wacc(
    beta: float,
    risk_free: float,
    market_premium: float,
    cost_of_debt: float,
    tax_rate: float,
    weight_equity: float,
    weight_debt: float,
) -> float:
    """
    WACC = (E/V) * Re + (D/V) * Rd * (1 - t)
    donde Re = Rf + beta * (Rm - Rf)  [CAPM]
    """
    if abs(weight_equity + weight_debt - 1.0) > 1e-6:
        raise ValueError("weight_equity + weight_debt debe sumar 1.0")
    cost_of_equity = risk_free + beta * market_premium
    after_tax_kd = cost_of_debt * (1 - tax_rate)
    return weight_equity * cost_of_equity + weight_debt * after_tax_kd


def dcf_model(inputs: DCFInputs) -> DCFResult:
    """DCF de dos etapas con terminal value (Gordon)."""
    if inputs.wacc <= inputs.terminal_growth:
        raise ValueError(
            f"WACC ({inputs.wacc:.2%}) debe ser > g terminal "
            f"({inputs.terminal_growth:.2%})."
        )
    
    # Determinar growth a usar
    g = inputs.growth_rate if inputs.growth_rate is not None else cagr(inputs.fcf_history)
    if not np.isfinite(g):
        g = 0.05  # Fallback razonable
    g = max(min(g, DCF_DEFAULTS["growth_cap_upper"]), DCF_DEFAULTS["growth_cap_lower"])
    
    fcf_clean = inputs.fcf_history.dropna()
    if fcf_clean.empty:
        raise ValueError("FCF histórico vacío.")
    last_fcf = float(fcf_clean.iloc[-1])
    
    if last_fcf <= 0:
        raise ValueError(
            f"FCF más reciente es <= 0 (${last_fcf:,.0f}). "
            "DCF estándar no aplica; considerá usar comparables o normalizar FCF."
        )
    
    years = np.arange(1, inputs.projection_years + 1)
    projected = pd.Series(
        [last_fcf * (1 + g) ** y for y in years],
        index=[f"Y+{y}" for y in years],
        name="FCF Proyectado",
    )
    discount_factors = 1 / (1 + inputs.wacc) ** years
    pv_fcf = pd.Series(
        projected.values * discount_factors, index=projected.index, name="PV FCF"
    )
    
    # Terminal Value en el año N
    tv = projected.iloc[-1] * (1 + inputs.terminal_growth) / (
        inputs.wacc - inputs.terminal_growth
    )
    pv_tv = tv / (1 + inputs.wacc) ** inputs.projection_years
    
    enterprise_value = float(pv_fcf.sum() + pv_tv)
    equity_value = enterprise_value - inputs.total_debt + inputs.cash
    intrinsic = equity_value / inputs.shares_outstanding if inputs.shares_outstanding else float("nan")
    
    return DCFResult(
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        intrinsic_per_share=intrinsic,
        projected_fcf=projected,
        pv_fcf=pv_fcf,
        terminal_value=tv,
        pv_terminal=pv_tv,
        growth_used=g,
        inputs=inputs,
    )


def build_dcf_inputs_from_company(
    company,
    wacc: float,
    terminal_growth: float = DCF_DEFAULTS["terminal_growth"],
    projection_years: int = DCF_DEFAULTS["projection_years"],
    growth_rate: Optional[float] = None,
) -> DCFInputs:
    """Helper para armar DCFInputs desde un CompanyData."""
    cash_df = company.cash_flow
    bs = company.balance_sheet
    
    ocf = _get(cash_df, "ocf")
    capex = _get(cash_df, "capex")
    if ocf is None or capex is None:
        raise ValueError("FCF no calculable: OCF o CAPEX faltantes.")
    fcf = ocf + capex  # capex negativo en yfinance
    
    debt_series = _get(bs, "total_debt")
    if debt_series is None:
        ltd = _get(bs, "long_term_debt")
        std = _get(bs, "short_term_debt")
        if ltd is not None:
            debt_series = ltd.add(std, fill_value=0) if std is not None else ltd
    cash_series = _get(bs, "cash_eq")
    
    total_debt = float(debt_series.dropna().iloc[-1]) if debt_series is not None else 0.0
    total_cash = float(cash_series.dropna().iloc[-1]) if cash_series is not None else 0.0
    
    shares = company.shares_outstanding
    if not shares:
        raise ValueError("sharesOutstanding no disponible para calcular precio por acción.")
    
    return DCFInputs(
        fcf_history=fcf,
        shares_outstanding=float(shares),
        total_debt=total_debt,
        cash=total_cash,
        wacc=wacc,
        terminal_growth=terminal_growth,
        projection_years=projection_years,
        growth_rate=growth_rate,
    )


def sensitivity_table(
    base_inputs: DCFInputs,
    wacc_range: tuple[float, float, int] = (0.07, 0.13, 7),
    g_range: tuple[float, float, int] = (0.015, 0.035, 5),
) -> pd.DataFrame:
    """
    Tabla de sensibilidad WACC vs terminal growth.
    Útil para mostrar cuán sensible es el intrínseco a los supuestos.
    """
    waccs = np.linspace(*wacc_range)
    gs = np.linspace(*g_range)
    table = pd.DataFrame(index=[f"{w:.1%}" for w in waccs], columns=[f"{g:.1%}" for g in gs])
    table.index.name = "WACC"
    table.columns.name = "g_terminal"
    
    for w in waccs:
        for g in gs:
            try:
                inp = DCFInputs(
                    fcf_history=base_inputs.fcf_history,
                    shares_outstanding=base_inputs.shares_outstanding,
                    total_debt=base_inputs.total_debt,
                    cash=base_inputs.cash,
                    wacc=w,
                    terminal_growth=g,
                    projection_years=base_inputs.projection_years,
                    growth_rate=base_inputs.growth_rate,
                )
                r = dcf_model(inp)
                table.loc[f"{w:.1%}", f"{g:.1%}"] = round(r.intrinsic_per_share, 2)
            except Exception:
                table.loc[f"{w:.1%}", f"{g:.1%}"] = np.nan
    return table.astype(float)
