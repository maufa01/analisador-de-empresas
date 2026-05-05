"""
WACC computed correctly: market-value capital structure, real cost of
debt, regression beta, Hamada de/relevering.

Pipeline:
1. Compute equity beta via OLS regression of monthly target log-returns
   on monthly benchmark log-returns over a 5-year window.
2. Unlever the beta with the **historical** D/E to get an asset beta.
3. Re-lever with the **target** D/E (typically current market-value
   capital structure) to get the equity beta we'll discount with.
4. Cost of equity from CAPM: ``Re = Rf + β_relevered * ERP``.
5. Cost of debt from financials: ``Rd = Interest Expense / avg Total Debt``.
6. Effective tax rate from the last 3 years' tax / EBIT.
7. WACC = (E/V) * Re + (D/V) * Rd * (1 - t).

We keep statsmodels optional — if it's not installed, fall back to a
numpy OLS that matches statsmodels' coefficient and standard error to
within floating-point tolerance.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .ratios import _get, effective_tax_rate
from core.constants import DEFAULT_WACC_PARAMS, BETA_REGRESSION
from core.exceptions import InsufficientDataError, ValuationError


# ============================================================
# Output
# ============================================================
@dataclass
class BetaResult:
    beta: float
    alpha: float
    r_squared: float
    n_observations: int
    method: str            # "statsmodels" | "numpy"
    std_error: float


@dataclass
class WACCResult:
    wacc: float
    cost_of_equity: float
    cost_of_debt_after_tax: float
    cost_of_debt_pretax: float
    weight_equity: float
    weight_debt: float
    tax_rate: float
    beta_relevered: float
    risk_free_rate: float
    equity_risk_premium: float


# ============================================================
# Beta regression
# ============================================================
def _to_log_returns(prices: pd.Series, freq: str = "M") -> pd.Series:
    """Resample to month-end and return log returns (drops first NaN)."""
    s = prices.dropna().astype(float)
    if freq.upper() in ("M", "MONTHLY"):
        s = s.resample("ME").last()
    elif freq.upper() in ("W", "WEEKLY"):
        s = s.resample("W-FRI").last()
    return np.log(s / s.shift(1)).dropna()


def compute_beta(
    target_prices: pd.Series,
    benchmark_prices: pd.Series,
    *,
    frequency: str = BETA_REGRESSION["frequency"],
    lookback_years: int = BETA_REGRESSION["lookback_years"],
) -> BetaResult:
    """
    OLS regression of target log-returns on benchmark log-returns.

    Both inputs may be raw price series (not log-returns) — we handle the
    transformation here. We trim to the last ``lookback_years`` of monthly
    observations.
    """
    if target_prices is None or benchmark_prices is None:
        raise InsufficientDataError("Both target and benchmark prices required")

    tr = _to_log_returns(target_prices, frequency)
    br = _to_log_returns(benchmark_prices, frequency)

    months = lookback_years * 12 if frequency.upper() in ("M", "MONTHLY") else lookback_years * 52
    df = pd.concat([tr, br], axis=1, join="inner").dropna()
    df.columns = ["y", "x"]
    df = df.tail(months)

    if len(df) < 24:
        raise InsufficientDataError(
            f"Need ≥24 observations for stable beta; got {len(df)}"
        )

    # Try statsmodels first
    try:
        import statsmodels.api as sm  # type: ignore
        X = sm.add_constant(df["x"].values)
        model = sm.OLS(df["y"].values, X).fit()
        return BetaResult(
            beta=float(model.params[1]),
            alpha=float(model.params[0]),
            r_squared=float(model.rsquared),
            n_observations=int(len(df)),
            method="statsmodels",
            std_error=float(model.bse[1]),
        )
    except ImportError:
        pass

    # numpy fallback — closed-form OLS with 2 parameters
    x = df["x"].values
    y = df["y"].values
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta_hat, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = float(beta_hat[0]), float(beta_hat[1])
    y_pred = X @ beta_hat
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    sigma2 = ss_res / max(n - 2, 1)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se_beta = float(np.sqrt(cov[1, 1]))
    return BetaResult(
        beta=beta, alpha=alpha, r_squared=r2,
        n_observations=n, method="numpy", std_error=se_beta,
    )


# ============================================================
# Hamada de/relevering
# ============================================================
def unlever_beta(
    beta_levered: float, debt_to_equity: float, tax_rate: float
) -> float:
    """β_unlevered = β_levered / (1 + (1 - t) * D/E)."""
    return float(beta_levered) / (1.0 + (1.0 - tax_rate) * float(debt_to_equity))


def relever_beta(
    beta_unlevered: float, target_debt_to_equity: float, tax_rate: float
) -> float:
    """β_relevered = β_unlevered * (1 + (1 - t) * D/E_target)."""
    return float(beta_unlevered) * (1.0 + (1.0 - tax_rate) * float(target_debt_to_equity))


# ============================================================
# Cost of debt — real, not bond-yield-implied
# ============================================================
def real_cost_of_debt(
    income: pd.DataFrame, balance: pd.DataFrame, *, periods: int = 3
) -> Optional[float]:
    """
    Cost of debt = Interest Expense_t / avg(Total Debt_{t}, Total Debt_{t-1}).

    Averaged over the last ``periods`` years to smooth noise. Returns None
    if either side is unavailable.
    """
    interest = _get(income, "interest_expense")
    debt = _get(balance, "total_debt")
    if interest is None or debt is None:
        ltd = _get(balance, "long_term_debt")
        std = _get(balance, "short_term_debt")
        if ltd is not None and std is not None:
            debt = ltd.add(std, fill_value=0.0)
        elif ltd is not None:
            debt = ltd
    if interest is None or debt is None:
        return None

    debt_clean = debt.dropna()
    if len(debt_clean) < 2:
        return None

    avg_debt = ((debt_clean + debt_clean.shift(1)) / 2.0).dropna()
    common = interest.dropna().index.intersection(avg_debt.index)
    if common.empty:
        return None

    rates = (interest.loc[common].abs() / avg_debt.loc[common]).tail(periods)
    rates = rates.replace([np.inf, -np.inf], np.nan).dropna()
    if rates.empty:
        return None
    rate = float(rates.mean())
    if not np.isfinite(rate) or rate < 0:
        return None
    return min(rate, 0.20)  # sanity clamp — anything above 20% is data noise


# ============================================================
# Capital structure — market values
# ============================================================
def market_capital_structure(
    market_cap: float, total_debt: float
) -> tuple[float, float]:
    """Returns (E/V, D/V) using market-value equity and book-value debt."""
    v = market_cap + total_debt
    if v <= 0:
        raise ValuationError("Total capital (E + D) is non-positive")
    return market_cap / v, total_debt / v


# ============================================================
# CAPM + WACC
# ============================================================
def capm_cost_of_equity(
    risk_free: float, beta: float, equity_risk_premium: float
) -> float:
    return float(risk_free + beta * equity_risk_premium)


def calculate_wacc(
    *,
    risk_free: float,
    equity_risk_premium: float,
    beta: float,
    cost_of_debt_pretax: float,
    tax_rate: float,
    weight_equity: float,
    weight_debt: float,
) -> WACCResult:
    """Standard WACC formula. Validates that weights sum to 1."""
    if abs(weight_equity + weight_debt - 1.0) > 1e-6:
        raise ValuationError("Capital structure weights must sum to 1.0")
    re = capm_cost_of_equity(risk_free, beta, equity_risk_premium)
    rd_after = cost_of_debt_pretax * (1.0 - tax_rate)
    wacc = weight_equity * re + weight_debt * rd_after
    return WACCResult(
        wacc=wacc,
        cost_of_equity=re,
        cost_of_debt_after_tax=rd_after,
        cost_of_debt_pretax=cost_of_debt_pretax,
        weight_equity=weight_equity,
        weight_debt=weight_debt,
        tax_rate=tax_rate,
        beta_relevered=beta,
        risk_free_rate=risk_free,
        equity_risk_premium=equity_risk_premium,
    )


# ============================================================
# End-to-end helper
# ============================================================
def wacc_from_company(
    *,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    market_cap: float,
    total_debt: float,
    risk_free: Optional[float] = None,
    equity_risk_premium: Optional[float] = None,
    beta_levered: Optional[float] = None,
    target_prices: Optional[pd.Series] = None,
    benchmark_prices: Optional[pd.Series] = None,
) -> WACCResult:
    """
    Compute WACC end-to-end from raw company data.

    Pass either ``beta_levered`` directly or both price series for
    regression. ``risk_free`` and ``equity_risk_premium`` default to
    ``DEFAULT_WACC_PARAMS`` if omitted.
    """
    rf = DEFAULT_WACC_PARAMS["risk_free_rate"] if risk_free is None else risk_free
    erp = (
        DEFAULT_WACC_PARAMS["market_risk_premium"]
        if equity_risk_premium is None
        else equity_risk_premium
    )
    tax = effective_tax_rate(income)

    # Beta
    if beta_levered is None:
        if target_prices is None or benchmark_prices is None:
            raise InsufficientDataError(
                "Provide beta_levered or both target_prices + benchmark_prices"
            )
        beta_levered = compute_beta(target_prices, benchmark_prices).beta

    # Capital structure (market value)
    we, wd = market_capital_structure(market_cap, total_debt)

    # Cost of debt — real, with fallback
    rd = real_cost_of_debt(income, balance)
    if rd is None:
        rd = DEFAULT_WACC_PARAMS["cost_of_debt"]

    return calculate_wacc(
        risk_free=rf,
        equity_risk_premium=erp,
        beta=beta_levered,
        cost_of_debt_pretax=rd,
        tax_rate=tax,
        weight_equity=we,
        weight_debt=wd,
    )
