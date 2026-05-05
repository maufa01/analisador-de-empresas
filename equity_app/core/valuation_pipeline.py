"""
Single orchestrator that turns ``Assumptions`` + the company's financials
into a complete ``ValuationResults`` bundle.

It runs the five valuation models (DCF, comparables, Monte Carlo, DDM,
Residual Income), aggregates them with sector weights, computes the
sub-score breakdown, and produces a final analyst rating.

Pipeline contract:
    inputs  → Assumptions, financials (income/balance/cash), peers,
              earnings-quality result, current price, sector
    output  → ValuationResults (a single dataclass with everything the
              UI needs to render)

Models that fail return None for that slot — the aggregator and the
scorer both tolerate sparse inputs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from analysis.assumptions import Assumptions
from analysis.earnings_quality import EarningsQuality
from analysis.wacc import calculate_wacc, WACCResult
from core.exceptions import InsufficientDataError, ValuationError
from valuation.dcf_three_stage import run_dcf, DCFResult
from valuation.comparables import (
    PeerSnapshot, TargetFundamentals,
    value_by_comparables, ComparablesResult,
)
from valuation.monte_carlo import run_monte_carlo, MonteCarloResult
from valuation.ddm import (
    is_applicable as ddm_is_applicable,
    two_stage as ddm_two_stage,
    DDMResult,
)
from valuation.residual_income import run_residual_income, RIResult
from valuation.valuation_aggregator import aggregate, AggregatedValuation
from scoring.scorer import compute_score, ScoreBreakdown
from scoring.rating import rate, Rating


_NO_DCF_TICKERS: set[str] = {"JPM", "BAC", "WFC", "C", "GS", "MS"}


@dataclass
class ValuationResults:
    """One dataclass with every artefact the page renders."""
    ticker: str
    sector: Optional[str]
    current_price: Optional[float]

    wacc: WACCResult
    dcf: Optional[DCFResult] = None
    dcf_error: Optional[str] = None
    comparables: Optional[ComparablesResult] = None
    comparables_error: Optional[str] = None
    monte_carlo: Optional[MonteCarloResult] = None
    monte_carlo_error: Optional[str] = None
    ddm: Optional[DDMResult] = None
    ddm_error: Optional[str] = None
    residual_income: Optional[RIResult] = None
    ri_error: Optional[str] = None

    aggregator: AggregatedValuation = field(default=None)  # type: ignore[assignment]
    score: ScoreBreakdown = field(default=None)            # type: ignore[assignment]
    rating: Rating = field(default=None)                   # type: ignore[assignment]


# ============================================================
# Internals
# ============================================================
def _build_target_fundamentals(
    income: pd.DataFrame, balance: pd.DataFrame
) -> Optional[TargetFundamentals]:
    """Construct TargetFundamentals from the latest year of statements."""
    if income.empty or balance.empty:
        return None
    last_inc = income.iloc[-1]
    last_bal = balance.iloc[-1]

    def _pick(row: pd.Series, *keys: str) -> Optional[float]:
        for k in keys:
            if k in row and pd.notna(row[k]):
                return float(row[k])
        return None

    shares = _pick(last_inc, "weightedAverageShsOut", "weightedAverageShsOutDil")
    if not shares or shares <= 0:
        return None
    return TargetFundamentals(
        net_income=_pick(last_inc, "netIncome"),
        revenue=_pick(last_inc, "revenue"),
        ebitda=_pick(last_inc, "ebitda"),
        book_value=_pick(last_bal, "totalStockholdersEquity", "totalEquity"),
        shares_outstanding=shares,
        cash=_pick(last_bal, "cashAndCashEquivalents") or 0.0,
        debt=_pick(last_bal, "totalDebt") or 0.0,
    )


# ============================================================
# Public API
# ============================================================
def run_valuation(
    *,
    ticker: str,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
    assumptions: Assumptions,
    peers: Optional[list[PeerSnapshot]] = None,
    earnings_quality: Optional[EarningsQuality] = None,
    current_price: Optional[float] = None,
    sector: Optional[str] = None,
    run_monte_carlo_now: bool = True,
    mc_seed: int = 42,
) -> ValuationResults:
    """
    Run every model the spec calls for and return a single bundle.

    ``run_monte_carlo_now=False`` lets the caller skip the slowest model
    when the user is mid-typing — the page can debounce and re-call with
    True once the inputs settle.
    """
    # ---- WACC (always — every other model needs it) ----
    wacc_res = calculate_wacc(
        risk_free=assumptions.risk_free,
        equity_risk_premium=assumptions.equity_risk_premium,
        beta=assumptions.beta,
        cost_of_debt_pretax=assumptions.cost_of_debt,
        tax_rate=assumptions.tax_rate,
        weight_equity=assumptions.weight_equity,
        weight_debt=assumptions.weight_debt,
    )
    out = ValuationResults(
        ticker=ticker, sector=sector, current_price=current_price, wacc=wacc_res,
    )

    g_override: Optional[float] = (
        assumptions.override_growth or None
    )

    # ---- DCF ----
    if ticker not in _NO_DCF_TICKERS:
        try:
            out.dcf = run_dcf(
                income=income, balance=balance, cash=cash,
                wacc=wacc_res.wacc,
                stage1_growth=g_override,
                stage1_years=assumptions.stage1_years,
                stage2_years=assumptions.stage2_years,
                terminal_growth=assumptions.terminal_growth,
            )
        except (ValuationError, InsufficientDataError) as exc:
            out.dcf_error = str(exc)
    else:
        out.dcf_error = "DCF on FCFF does not apply to financials."

    # ---- Comparables ----
    if peers:
        target = _build_target_fundamentals(income, balance)
        if target is None:
            out.comparables_error = "Could not build target fundamentals."
        else:
            try:
                out.comparables = value_by_comparables(
                    peers=peers, target=target,
                )
            except (ValuationError, InsufficientDataError) as exc:
                out.comparables_error = str(exc)
    else:
        out.comparables_error = "No peers configured."

    # ---- Monte Carlo (slowest — wraps DCF) ----
    if run_monte_carlo_now and out.dcf is not None:
        try:
            out.monte_carlo = run_monte_carlo(
                income=income, balance=balance, cash=cash,
                wacc=wacc_res.wacc,
                n_simulations=int(assumptions.mc_n_simulations),
                wacc_std=assumptions.mc_wacc_std,
                terminal_low=assumptions.mc_terminal_low,
                terminal_high=assumptions.mc_terminal_high,
                stage1_years=assumptions.stage1_years,
                stage2_years=assumptions.stage2_years,
                growth_std=assumptions.mc_rev_growth_std,
                current_price=current_price,
                seed=mc_seed,
            )
        except (ValuationError, InsufficientDataError) as exc:
            out.monte_carlo_error = str(exc)
    elif out.dcf is None:
        out.monte_carlo_error = "Requires a successful DCF run."
    else:
        out.monte_carlo_error = "Monte Carlo skipped (toggle to enable)."

    # ---- DDM ----
    if ddm_is_applicable(cash, income):
        try:
            out.ddm = ddm_two_stage(
                income=income, balance=balance, cash=cash,
                cost_of_equity=wacc_res.cost_of_equity,
                stage1_years=assumptions.stage1_years,
                terminal_growth=assumptions.terminal_growth,
            )
        except (ValuationError, InsufficientDataError) as exc:
            out.ddm_error = str(exc)
    else:
        out.ddm_error = "Company does not pay material dividends."

    # ---- Residual Income ----
    try:
        out.residual_income = run_residual_income(
            income=income, balance=balance,
            cost_of_equity=wacc_res.cost_of_equity,
            stage1_years=assumptions.stage1_years,
            stage1_growth=g_override,
            terminal_growth=assumptions.terminal_growth,
        )
    except (ValuationError, InsufficientDataError) as exc:
        out.ri_error = str(exc)

    # ---- Aggregator ----
    out.aggregator = aggregate(
        dcf=(out.dcf.intrinsic_value_per_share if out.dcf else None),
        comparables=(
            out.comparables.implied_per_share_median
            if out.comparables and out.comparables.implied_per_share_median
            else None
        ),
        monte_carlo=(out.monte_carlo.median if out.monte_carlo else None),
        ddm=(out.ddm.intrinsic_value_per_share if out.ddm else None),
        residual_income=(
            out.residual_income.intrinsic_value_per_share
            if out.residual_income else None
        ),
        sector=sector,
    )

    # ---- Scoring + Rating ----
    upside: Optional[float] = None
    if (np.isfinite(out.aggregator.intrinsic_per_share)
            and current_price and current_price > 0):
        upside = (out.aggregator.intrinsic_per_share - current_price) / current_price

    out.score = compute_score(
        income=income, balance=balance, cash=cash,
        earnings_quality=earnings_quality,
        intrinsic=(out.aggregator.intrinsic_per_share
                   if np.isfinite(out.aggregator.intrinsic_per_share) else None),
        current_price=current_price,
    )
    out.rating = rate(
        composite=out.score.composite,
        upside=upside,
        confidence=out.aggregator.confidence,
    )
    return out
