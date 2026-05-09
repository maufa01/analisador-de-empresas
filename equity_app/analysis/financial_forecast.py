"""
Multi-year financial-statement projection engine.

Reuses the growth-path helper from :mod:`valuation.dcf_three_stage` so
the forecast is consistent with the DCF model. Inputs default to
historical averages and are individually overridable.

Design choices
--------------
- Income statement: top-down — revenue path × margin paths → income items
- Cash flow:        OCF margin × revenue → CFO; capex % rev → capex
- Balance sheet:    simple roll-forward (cash + retained earnings; debt
                    pay-down). Working-capital modelling via DSO/DIO/DPO
                    is exposed in :class:`ForecastInputs` but NOT yet
                    consumed — flagged TODO.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, free_cash_flow, cagr
from valuation.dcf_three_stage import _build_growth_path, FadeCurve


# ============================================================
# Dataclasses
# ============================================================
@dataclass
class ForecastInputs:
    """Per-line inputs for the forecast. All optional — defaults from
    historical when omitted."""
    revenue_growth_path: Optional[list[float]] = None
    gross_margin_path:     Optional[list[float]] = None
    operating_margin_path: Optional[list[float]] = None
    net_margin_path:       Optional[list[float]] = None
    ebitda_margin_path:    Optional[list[float]] = None

    ocf_margin:        Optional[float] = None
    capex_pct_revenue: Optional[float] = None
    sbc_pct_revenue:   Optional[float] = None

    tax_rate: Optional[float] = None

    dso: Optional[float] = None
    dio: Optional[float] = None
    dpo: Optional[float] = None

    debt_repayment_pct: float = 0.0
    buyback_pct_fcf: float = 0.0
    dividend_payout_ratio: Optional[float] = None

    years: int = 5
    fade_curve: FadeCurve = "linear"


@dataclass
class ForecastResult:
    income_projected: pd.DataFrame
    balance_projected: pd.DataFrame
    cash_flow_projected: pd.DataFrame

    fcff_per_year: pd.Series
    fcff_adjusted_per_year: pd.Series       # net of SBC
    fcf_per_share: pd.Series
    cumulative_fcf: pd.Series

    inputs_used: ForecastInputs
    base_year: int
    warnings: list[str] = field(default_factory=list)


# ============================================================
# Defaults from history
# ============================================================
def _default_inputs_from_history(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    years: int = 5,
    growth_clamp: tuple[float, float] = (-0.05, 0.30),
) -> ForecastInputs:
    """Build default inputs from the company's own historical data."""
    rev = _get(income, "revenue")
    hist_growth = cagr(rev, periods=5) if rev is not None else 0.05
    if not np.isfinite(hist_growth):
        hist_growth = 0.05
    g1 = float(np.clip(hist_growth, *growth_clamp))
    growth_path = _build_growth_path(g1, 0.025, years, 0, "linear")

    def _avg_margin(num_key: str, denom_key: str = "revenue",
                    periods: int = 3) -> Optional[float]:
        num = _get(income, num_key)
        denom = _get(income, denom_key)
        if num is None or denom is None:
            return None
        ratios = (num / denom.replace(0, np.nan)).dropna().tail(periods)
        if ratios.empty:
            return None
        avg = float(ratios.mean())
        return avg if np.isfinite(avg) else None

    gross_m = _avg_margin("gross_profit")
    op_m = _avg_margin("operating_income")
    net_m = _avg_margin("net_income")
    ebitda_m = _avg_margin("ebitda")

    ocf = _get(cash, "ocf")
    if ocf is not None and rev is not None:
        ratios = (ocf / rev.replace(0, np.nan)).dropna().tail(3)
        ocf_m = float(ratios.mean()) if not ratios.empty else None
    else:
        ocf_m = None

    capex = _get(cash, "capex")
    if capex is not None and rev is not None:
        ratios = (capex.abs() / rev.replace(0, np.nan)).dropna().tail(3)
        capex_pct = float(ratios.mean()) if not ratios.empty else None
    else:
        capex_pct = None

    sbc = _get(cash, "sbc")
    sbc_pct: float = 0.0
    if sbc is not None and rev is not None:
        ratios = (sbc / rev.replace(0, np.nan)).dropna().tail(3)
        if not ratios.empty:
            sbc_pct = float(ratios.mean())

    return ForecastInputs(
        revenue_growth_path=[float(g) for g in growth_path],
        gross_margin_path=([gross_m] * years) if gross_m is not None else None,
        operating_margin_path=([op_m] * years) if op_m is not None else None,
        net_margin_path=([net_m] * years) if net_m is not None else None,
        ebitda_margin_path=([ebitda_m] * years) if ebitda_m is not None else None,
        ocf_margin=ocf_m,
        capex_pct_revenue=capex_pct,
        sbc_pct_revenue=sbc_pct if np.isfinite(sbc_pct) else 0.0,
        years=years,
    )


# ============================================================
# Projection helpers
# ============================================================
def _future_index(last_actual_index, years: int) -> pd.Index:
    """Build the projection's DateTime index from the last actual row."""
    if isinstance(last_actual_index, pd.Timestamp):
        return pd.date_range(
            start=last_actual_index + pd.DateOffset(years=1),
            periods=years, freq="YE",
        )
    return pd.RangeIndex(start=1, stop=years + 1)


def _project_income(
    last_actual: pd.Series,
    inputs: ForecastInputs,
    years: int,
) -> pd.DataFrame:
    """Project income statement N years forward."""
    rows = []
    rev_t = float(last_actual["revenue"])
    for t in range(years):
        g = inputs.revenue_growth_path[t]
        rev_t = rev_t * (1.0 + g)

        row: dict[str, float] = {"revenue": rev_t}
        if inputs.gross_margin_path:
            row["grossProfit"] = rev_t * inputs.gross_margin_path[t]
            row["costOfRevenue"] = rev_t - row["grossProfit"]
        if inputs.operating_margin_path:
            row["operatingIncome"] = rev_t * inputs.operating_margin_path[t]
            row["ebit"] = row["operatingIncome"]
        if inputs.ebitda_margin_path:
            row["ebitda"] = rev_t * inputs.ebitda_margin_path[t]
        if inputs.net_margin_path:
            row["netIncome"] = rev_t * inputs.net_margin_path[t]

        # Pretax + tax expense reconstructed only when tax_rate provided
        if inputs.tax_rate is not None and "netIncome" in row:
            denom = 1.0 - float(inputs.tax_rate)
            if denom > 0:
                row["incomeBeforeTax"] = row["netIncome"] / denom
                row["incomeTaxExpense"] = (
                    row["incomeBeforeTax"] - row["netIncome"]
                )

        rows.append(row)

    return pd.DataFrame(rows, index=_future_index(last_actual.name, years))


def _project_cash_flow(
    income_proj: pd.DataFrame,
    inputs: ForecastInputs,
) -> pd.DataFrame:
    """Project cash flow from projected income."""
    rows: list[dict[str, float]] = []
    for idx in income_proj.index:
        rev = float(income_proj.loc[idx, "revenue"])
        row: dict[str, float] = {}
        if inputs.ocf_margin is not None:
            row["operatingCashFlow"] = rev * inputs.ocf_margin
        if inputs.capex_pct_revenue is not None:
            capex = -abs(rev * inputs.capex_pct_revenue)
            row["capitalExpenditure"] = capex
            if "operatingCashFlow" in row:
                row["freeCashFlow"] = row["operatingCashFlow"] + capex
        if inputs.sbc_pct_revenue is not None:
            row["stockBasedCompensation"] = rev * inputs.sbc_pct_revenue
        rows.append(row)
    return pd.DataFrame(rows, index=income_proj.index)


def _project_balance(
    last_actual_balance: pd.Series,
    income_proj: pd.DataFrame,
    cash_proj: pd.DataFrame,
    inputs: ForecastInputs,
) -> pd.DataFrame:
    """Simplified balance roll-forward.

    - Cash grows by retained FCF
    - Debt declines at debt_repayment_pct
    - Equity grows by retained earnings (NI × (1 − payout))

    Working-capital roll-forward via DSO/DIO/DPO is intentionally NOT
    modelled here — it requires richer assumptions and is flagged TODO.
    """
    rows: list[dict[str, float]] = []
    cash_t = float(last_actual_balance.get("cashAndCashEquivalents", 0.0) or 0.0)
    debt_t = float(last_actual_balance.get("totalDebt", 0.0) or 0.0)
    equity_t = float(last_actual_balance.get("totalStockholdersEquity", 0.0) or 0.0)

    payout = float(inputs.dividend_payout_ratio or 0.0)
    buyback_pct = float(inputs.buyback_pct_fcf or 0.0)

    for idx in income_proj.index:
        ni = float(income_proj.loc[idx].get("netIncome", 0.0) or 0.0)
        fcf = float(cash_proj.loc[idx].get("freeCashFlow", 0.0)) if idx in cash_proj.index else 0.0

        retained = fcf * (1.0 - payout - buyback_pct)
        cash_t = cash_t + retained
        debt_t = debt_t * (1.0 - inputs.debt_repayment_pct)
        equity_t = equity_t + ni * (1.0 - payout)

        rows.append({
            "cashAndCashEquivalents":   cash_t,
            "totalDebt":                debt_t,
            "totalStockholdersEquity":  equity_t,
        })

    return pd.DataFrame(rows, index=income_proj.index)


# ============================================================
# Public API
# ============================================================
def project_financials(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    inputs: Optional[ForecastInputs] = None,
    years: int = 5,
    shares_outstanding: Optional[float] = None,
) -> ForecastResult:
    """End-to-end forecast: income → cash flow → balance → conv. series."""
    if income.empty or balance.empty or cash.empty:
        raise ValueError("All three financial statements required")

    if inputs is None:
        inputs = _default_inputs_from_history(income, balance, cash, years)
    elif (inputs.revenue_growth_path is None
            or len(inputs.revenue_growth_path) < years):
        # Pad / shrink the growth path to the requested horizon
        defaults = _default_inputs_from_history(income, balance, cash, years)
        inputs.revenue_growth_path = defaults.revenue_growth_path

    last_inc = income.iloc[-1]
    last_bal = balance.iloc[-1]

    income_proj = _project_income(last_inc, inputs, years)
    cash_proj = _project_cash_flow(income_proj, inputs)
    balance_proj = _project_balance(last_bal, income_proj, cash_proj, inputs)

    fcff = (cash_proj["freeCashFlow"]
            if "freeCashFlow" in cash_proj.columns
            else pd.Series(dtype=float))
    sbc = (cash_proj["stockBasedCompensation"]
           if "stockBasedCompensation" in cash_proj.columns
           else pd.Series(0.0, index=fcff.index))
    fcff_adj = fcff - sbc.reindex(fcff.index).fillna(0.0)
    cum = fcff.cumsum() if not fcff.empty else fcff

    fcf_per_share = pd.Series(dtype=float)
    if shares_outstanding and shares_outstanding > 0 and not fcff.empty:
        fcf_per_share = fcff / float(shares_outstanding)

    base_year = (
        last_inc.name.year
        if isinstance(last_inc.name, pd.Timestamp) else 0
    )

    return ForecastResult(
        income_projected=income_proj,
        balance_projected=balance_proj,
        cash_flow_projected=cash_proj,
        fcff_per_year=fcff,
        fcff_adjusted_per_year=fcff_adj,
        fcf_per_share=fcf_per_share,
        cumulative_fcf=cum,
        inputs_used=inputs,
        base_year=base_year,
    )


def project_bull_bear_base(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    base_inputs: ForecastInputs,
    years: int = 5,
) -> dict[str, ForecastResult]:
    """Run base / bull / bear scenarios with margin + growth tilts.

    - Bull: +30% growth, +200bp op margin, +150bp net margin
    - Bear: -50% growth, -200bp margins, +10% relative capex
    """
    def _scale_path(path, factor):
        return [v * factor for v in path] if path else None

    def _shift_path(path, delta, floor=None):
        if not path:
            return None
        if floor is not None:
            return [max(floor, v + delta) for v in path]
        return [v + delta for v in path]

    bull_inputs = ForecastInputs(
        revenue_growth_path=_scale_path(base_inputs.revenue_growth_path, 1.3),
        gross_margin_path=base_inputs.gross_margin_path,
        operating_margin_path=_shift_path(base_inputs.operating_margin_path, 0.02),
        net_margin_path=_shift_path(base_inputs.net_margin_path, 0.015),
        ebitda_margin_path=_shift_path(base_inputs.ebitda_margin_path, 0.02),
        ocf_margin=(base_inputs.ocf_margin * 1.05
                    if base_inputs.ocf_margin is not None else None),
        capex_pct_revenue=base_inputs.capex_pct_revenue,
        sbc_pct_revenue=base_inputs.sbc_pct_revenue,
        tax_rate=base_inputs.tax_rate,
        years=years,
    )

    bear_inputs = ForecastInputs(
        revenue_growth_path=_scale_path(base_inputs.revenue_growth_path, 0.5),
        gross_margin_path=base_inputs.gross_margin_path,
        operating_margin_path=_shift_path(base_inputs.operating_margin_path, -0.02, floor=0.0),
        net_margin_path=_shift_path(base_inputs.net_margin_path, -0.015, floor=0.0),
        ebitda_margin_path=_shift_path(base_inputs.ebitda_margin_path, -0.02, floor=0.0),
        ocf_margin=(base_inputs.ocf_margin * 0.95
                    if base_inputs.ocf_margin is not None else None),
        capex_pct_revenue=((base_inputs.capex_pct_revenue or 0.0) * 1.10
                           if base_inputs.capex_pct_revenue is not None else None),
        sbc_pct_revenue=base_inputs.sbc_pct_revenue,
        tax_rate=base_inputs.tax_rate,
        years=years,
    )

    return {
        "base": project_financials(income, balance, cash, base_inputs, years),
        "bull": project_financials(income, balance, cash, bull_inputs, years),
        "bear": project_financials(income, balance, cash, bear_inputs, years),
    }
