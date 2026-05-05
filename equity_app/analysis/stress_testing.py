"""
Stress testing — recompute DCF intrinsic under adverse scenarios.

Four scenario families:
    - Rates shock (parallel risk-free shifts → WACC → intrinsic + duration)
    - USD strength shock (revenue impact via international-revenue heuristic)
    - Recession (calibrated 2008 / 2020 / 1970s / 2000-dotcom shocks)
    - Sector-specific shocks (industry-keyed dictionaries)

Each function takes already-fetched income/balance/cash dataframes and a
base ``Assumptions`` object so the page does not pay yfinance twice. The
DCF is re-run via ``valuation.dcf_three_stage.run_dcf`` for each shocked
parameter set.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from analysis.assumptions import Assumptions
from analysis.wacc import calculate_wacc
from core.exceptions import ValuationError, InsufficientDataError
from valuation.dcf_three_stage import run_dcf


# ============================================================
# Result types
# ============================================================
@dataclass
class RatesScenario:
    shock_bps: int
    new_risk_free: float
    new_wacc: float
    wacc_delta_bps: int
    intrinsic: float
    change_from_base_pct: float
    vs_current_price_pct: Optional[float]


@dataclass
class RatesShockResult:
    base_intrinsic: float
    base_wacc: float
    current_price: Optional[float]
    scenarios: list[RatesScenario]
    modified_duration: Optional[float]
    interpretation: str


@dataclass
class GrowthScenario:
    name: str
    shock_pct: float
    new_growth: float
    intrinsic: float
    change_pct: float


@dataclass
class USDShockResult:
    applicable: bool
    international_pct: Optional[float]
    base_intrinsic: Optional[float]
    scenarios: list[GrowthScenario]
    note: str


@dataclass
class RecessionScenario:
    scenario_id: str
    scenario_name: str
    intrinsic: float
    change_pct: float
    duration_months: int
    revenue_decline_yr1: float
    margin_compression: float
    wacc_shock: float


@dataclass
class RecessionResult:
    base_intrinsic: float
    scenarios: list[RecessionScenario]


@dataclass
class SectorShockScenario:
    name: str
    intrinsic: float
    change_pct: float
    growth_impact: float
    margin_impact: float


@dataclass
class SectorShockResult:
    applicable: bool
    sector: Optional[str]
    base_intrinsic: Optional[float]
    scenarios: list[SectorShockScenario]
    note: str


# ============================================================
# DCF runner — same shape used by every scenario
# ============================================================
def _run_dcf_with(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    wacc: float, terminal_growth: float, stage1_growth: Optional[float],
    stage1_years: int, stage2_years: int,
) -> Optional[float]:
    try:
        r = run_dcf(
            income=income, balance=balance, cash=cash,
            wacc=wacc, terminal_growth=terminal_growth,
            stage1_growth=stage1_growth,
            stage1_years=stage1_years, stage2_years=stage2_years,
        )
        return float(r.intrinsic_value_per_share)
    except (ValuationError, InsufficientDataError):
        return None


def _wacc_with_risk_free(assumptions: Assumptions, new_rf: float) -> float:
    """Recompute WACC keeping every other input fixed except risk-free."""
    res = calculate_wacc(
        risk_free=new_rf,
        equity_risk_premium=assumptions.equity_risk_premium,
        beta=assumptions.beta,
        cost_of_debt_pretax=assumptions.cost_of_debt,
        tax_rate=assumptions.tax_rate,
        weight_equity=assumptions.weight_equity,
        weight_debt=assumptions.weight_debt,
    )
    return float(res.wacc)


def _historical_growth(cash: pd.DataFrame) -> Optional[float]:
    """Effective stage-1 growth — historical FCF CAGR clipped same as DCF."""
    from valuation.dcf_three_stage import _historical_fcf_cagr
    return _historical_fcf_cagr(cash)


# ============================================================
# A — Rates shock
# ============================================================
def stress_test_rates(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    assumptions: Assumptions, current_price: Optional[float],
    shocks_bps: tuple[int, ...] = (50, 100, 150, 200, 250),
) -> Optional[RatesShockResult]:
    base_wacc = _wacc_with_risk_free(assumptions, assumptions.risk_free)
    base_intrinsic = _run_dcf_with(
        income=income, balance=balance, cash=cash,
        wacc=base_wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_growth=(assumptions.override_growth or None),
        stage1_years=assumptions.stage1_years,
        stage2_years=assumptions.stage2_years,
    )
    if base_intrinsic is None:
        return None

    scenarios: list[RatesScenario] = []
    for bps in shocks_bps:
        new_rf = assumptions.risk_free + bps / 10000.0
        new_wacc = _wacc_with_risk_free(assumptions, new_rf)
        new_intr = _run_dcf_with(
            income=income, balance=balance, cash=cash,
            wacc=new_wacc,
            terminal_growth=assumptions.terminal_growth,
            stage1_growth=(assumptions.override_growth or None),
            stage1_years=assumptions.stage1_years,
            stage2_years=assumptions.stage2_years,
        )
        if new_intr is None:
            continue
        vs_price = (
            (new_intr / current_price - 1.0) * 100
            if current_price and current_price > 0 else None
        )
        scenarios.append(RatesScenario(
            shock_bps=int(bps),
            new_risk_free=float(new_rf),
            new_wacc=float(new_wacc),
            wacc_delta_bps=int(round((new_wacc - base_wacc) * 10000)),
            intrinsic=float(new_intr),
            change_from_base_pct=float((new_intr / base_intrinsic - 1.0) * 100),
            vs_current_price_pct=vs_price,
        ))

    duration: Optional[float] = None
    if scenarios:
        first = scenarios[0]
        if first.shock_bps > 0:
            duration = -(first.change_from_base_pct / 100.0) / (first.shock_bps / 10000.0)

    return RatesShockResult(
        base_intrinsic=float(base_intrinsic),
        base_wacc=float(base_wacc),
        current_price=current_price,
        scenarios=scenarios,
        modified_duration=duration,
        interpretation=_interpret_duration(duration),
    )


def _interpret_duration(d: Optional[float]) -> str:
    if d is None:
        return "Not enough scenarios to estimate duration."
    if d > 15:
        return f"Extreme rate sensitivity (duration {d:.1f}). Long-duration cash flows."
    if d > 10:
        return f"High rate sensitivity (duration {d:.1f}). Growth/tech profile."
    if d > 5:
        return f"Moderate rate sensitivity (duration {d:.1f})."
    return f"Low rate sensitivity (duration {d:.1f}). Stable cash flows."


# ============================================================
# B — USD strength shock
# ============================================================
_SECTOR_INTL_DEFAULTS = {
    "Technology":            0.55,
    "Communication Services": 0.40,
    "Healthcare":            0.45,
    "Consumer Cyclical":     0.40,
    "Consumer Defensive":    0.35,
    "Industrials":           0.45,
    "Energy":                0.40,
    "Financial Services":    0.25,
    "Real Estate":           0.10,
    "Utilities":             0.05,
    "Basic Materials":       0.50,
}


def estimate_international_revenue_pct(
    *, sector: Optional[str], country: Optional[str] = "United States"
) -> float:
    """Heuristic — no FMP segments data. Sector + domicile only."""
    if country and country != "United States":
        return 0.70
    return _SECTOR_INTL_DEFAULTS.get(sector or "", 0.30)


def stress_test_usd(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    assumptions: Assumptions, sector: Optional[str], country: Optional[str] = None,
    shocks_pct: tuple[float, ...] = (5, 10, 15, 20),
) -> USDShockResult:
    intl = estimate_international_revenue_pct(sector=sector, country=country)
    if intl < 0.10:
        return USDShockResult(
            applicable=False,
            international_pct=intl,
            base_intrinsic=None,
            scenarios=[],
            note="Revenue mostly USA-based (<10% international) — USD shocks negligible.",
        )

    base_wacc = _wacc_with_risk_free(assumptions, assumptions.risk_free)
    eff_growth = (
        assumptions.override_growth
        if assumptions.override_growth
        else _historical_growth(cash) or 0.0
    )
    base_intrinsic = _run_dcf_with(
        income=income, balance=balance, cash=cash,
        wacc=base_wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_growth=(assumptions.override_growth or None),
        stage1_years=assumptions.stage1_years,
        stage2_years=assumptions.stage2_years,
    )
    if base_intrinsic is None:
        return USDShockResult(
            applicable=False, international_pct=intl, base_intrinsic=None,
            scenarios=[], note="Base DCF could not be computed.",
        )

    scenarios: list[GrowthScenario] = []
    for shock in shocks_pct:
        # USD up X% → revenue impact ≈ -X * 0.5 * intl% (partial pricing power)
        rev_impact = -(shock / 100.0) * 0.5 * intl
        new_growth = max(-0.10, eff_growth + rev_impact)
        new_intr = _run_dcf_with(
            income=income, balance=balance, cash=cash,
            wacc=base_wacc,
            terminal_growth=assumptions.terminal_growth,
            stage1_growth=new_growth,
            stage1_years=assumptions.stage1_years,
            stage2_years=assumptions.stage2_years,
        )
        if new_intr is None:
            continue
        scenarios.append(GrowthScenario(
            name=f"USD +{shock:.0f}%",
            shock_pct=float(shock),
            new_growth=float(new_growth),
            intrinsic=float(new_intr),
            change_pct=float((new_intr / base_intrinsic - 1.0) * 100),
        ))

    return USDShockResult(
        applicable=True,
        international_pct=intl,
        base_intrinsic=float(base_intrinsic),
        scenarios=scenarios,
        note=("International revenue estimated from sector heuristic "
              "(no segment data without FMP)."),
    )


# ============================================================
# C — Recession scenarios
# ============================================================
HISTORICAL_RECESSIONS: dict[str, dict] = {
    "2008_GFC": {
        "name": "2008 Global Financial Crisis",
        "revenue_decline_yr1": -0.15,
        "margin_compression":  -0.05,
        "wacc_shock":           0.015,
        "duration_months":      18,
    },
    "2020_COVID": {
        "name": "2020 COVID Crash",
        "revenue_decline_yr1": -0.08,
        "margin_compression":  -0.02,
        "wacc_shock":           0.005,
        "duration_months":       6,
    },
    "1970s_stagflation": {
        "name": "1970s Stagflation",
        "revenue_decline_yr1": -0.05,
        "margin_compression":  -0.05,
        "wacc_shock":           0.025,
        "duration_months":      36,
    },
    "2000_dotcom": {
        "name": "2000 Dot-com Bust",
        "revenue_decline_yr1": -0.12,
        "margin_compression":  -0.06,
        "wacc_shock":           0.010,
        "duration_months":      24,
    },
}


def stress_test_recession(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    assumptions: Assumptions,
) -> Optional[RecessionResult]:
    base_wacc = _wacc_with_risk_free(assumptions, assumptions.risk_free)
    eff_growth = (
        assumptions.override_growth
        if assumptions.override_growth
        else _historical_growth(cash) or 0.0
    )
    base_intrinsic = _run_dcf_with(
        income=income, balance=balance, cash=cash,
        wacc=base_wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_growth=(assumptions.override_growth or None),
        stage1_years=assumptions.stage1_years,
        stage2_years=assumptions.stage2_years,
    )
    if base_intrinsic is None:
        return None

    scenarios: list[RecessionScenario] = []
    for sid, sh in HISTORICAL_RECESSIONS.items():
        new_rf = assumptions.risk_free + sh["wacc_shock"]
        new_wacc = _wacc_with_risk_free(assumptions, new_rf)
        # Margin compression bleeds into stage-1 growth as a proxy
        # (no margin parameter in run_dcf signature).
        new_growth = max(-0.20, eff_growth + sh["revenue_decline_yr1"] + sh["margin_compression"])
        new_intr = _run_dcf_with(
            income=income, balance=balance, cash=cash,
            wacc=new_wacc,
            terminal_growth=assumptions.terminal_growth,
            stage1_growth=new_growth,
            stage1_years=assumptions.stage1_years,
            stage2_years=assumptions.stage2_years,
        )
        if new_intr is None:
            continue
        scenarios.append(RecessionScenario(
            scenario_id=sid,
            scenario_name=sh["name"],
            intrinsic=float(new_intr),
            change_pct=float((new_intr / base_intrinsic - 1.0) * 100),
            duration_months=int(sh["duration_months"]),
            revenue_decline_yr1=float(sh["revenue_decline_yr1"]),
            margin_compression=float(sh["margin_compression"]),
            wacc_shock=float(sh["wacc_shock"]),
        ))

    return RecessionResult(base_intrinsic=float(base_intrinsic), scenarios=scenarios)


# ============================================================
# D — Sector-specific shocks
# ============================================================
SECTOR_SHOCKS: dict[str, list[dict]] = {
    "Technology": [
        {"name": "Antitrust regulation",   "growth_impact": -0.05, "margin_impact": -0.10},
        {"name": "AI capex ROI miss",      "growth_impact": -0.03, "margin_impact": -0.05},
        {"name": "China decoupling",       "growth_impact": -0.08, "margin_impact": -0.03},
    ],
    "Energy": [
        {"name": "Oil $40",                "growth_impact": -0.25, "margin_impact": -0.15},
        {"name": "Renewable transition",   "growth_impact": -0.10, "margin_impact": -0.05},
    ],
    "Financial Services": [
        {"name": "Yield curve flat",       "growth_impact": -0.03, "margin_impact": -0.05},
        {"name": "Credit cycle turn",      "growth_impact": -0.08, "margin_impact": -0.10},
        {"name": "Regulatory tightening",  "growth_impact": -0.02, "margin_impact": -0.03},
    ],
    "Healthcare": [
        {"name": "Drug pricing reform",    "growth_impact": -0.05, "margin_impact": -0.08},
        {"name": "Patent cliff",           "growth_impact": -0.15, "margin_impact": -0.05},
    ],
    "Consumer Cyclical": [
        {"name": "Consumer recession",     "growth_impact": -0.15, "margin_impact": -0.04},
        {"name": "Input cost spike",       "growth_impact":  0.00, "margin_impact": -0.05},
    ],
    "Consumer Defensive": [
        {"name": "Private-label competition", "growth_impact": -0.02, "margin_impact": -0.04},
    ],
    "Real Estate": [
        {"name": "Cap-rate +100bps",       "growth_impact": -0.10, "margin_impact":  0.00},
        {"name": "Office vacancy spike",   "growth_impact": -0.15, "margin_impact": -0.05},
    ],
    "Industrials": [
        {"name": "Cycle downturn",         "growth_impact": -0.10, "margin_impact": -0.05},
    ],
}


def stress_test_sector(
    *, income: pd.DataFrame, balance: pd.DataFrame, cash: pd.DataFrame,
    assumptions: Assumptions, sector: Optional[str],
) -> SectorShockResult:
    if not sector or sector not in SECTOR_SHOCKS:
        return SectorShockResult(
            applicable=False, sector=sector, base_intrinsic=None,
            scenarios=[],
            note=(f"No sector-specific shocks defined for "
                  f"{sector or 'unknown sector'}."),
        )

    base_wacc = _wacc_with_risk_free(assumptions, assumptions.risk_free)
    eff_growth = (
        assumptions.override_growth
        if assumptions.override_growth
        else _historical_growth(cash) or 0.0
    )
    base_intrinsic = _run_dcf_with(
        income=income, balance=balance, cash=cash,
        wacc=base_wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_growth=(assumptions.override_growth or None),
        stage1_years=assumptions.stage1_years,
        stage2_years=assumptions.stage2_years,
    )
    if base_intrinsic is None:
        return SectorShockResult(
            applicable=False, sector=sector, base_intrinsic=None,
            scenarios=[], note="Base DCF could not be computed.",
        )

    shocks = SECTOR_SHOCKS[sector]
    scenarios: list[SectorShockScenario] = []
    for sh in shocks:
        # Margin impact bleeds into growth as proxy (same reason as recession).
        new_growth = max(
            -0.20,
            eff_growth + sh.get("growth_impact", 0) + sh.get("margin_impact", 0),
        )
        new_intr = _run_dcf_with(
            income=income, balance=balance, cash=cash,
            wacc=base_wacc,
            terminal_growth=assumptions.terminal_growth,
            stage1_growth=new_growth,
            stage1_years=assumptions.stage1_years,
            stage2_years=assumptions.stage2_years,
        )
        if new_intr is None:
            continue
        scenarios.append(SectorShockScenario(
            name=sh["name"],
            intrinsic=float(new_intr),
            change_pct=float((new_intr / base_intrinsic - 1.0) * 100),
            growth_impact=float(sh.get("growth_impact", 0)),
            margin_impact=float(sh.get("margin_impact", 0)),
        ))

    # Combined scenario
    total_g = sum(sh.get("growth_impact", 0) for sh in shocks)
    total_m = sum(sh.get("margin_impact", 0) for sh in shocks)
    combined_growth = max(-0.30, eff_growth + total_g + total_m)
    combined_intr = _run_dcf_with(
        income=income, balance=balance, cash=cash,
        wacc=base_wacc,
        terminal_growth=assumptions.terminal_growth,
        stage1_growth=combined_growth,
        stage1_years=assumptions.stage1_years,
        stage2_years=assumptions.stage2_years,
    )
    if combined_intr is not None:
        scenarios.append(SectorShockScenario(
            name="All shocks combined",
            intrinsic=float(combined_intr),
            change_pct=float((combined_intr / base_intrinsic - 1.0) * 100),
            growth_impact=float(total_g),
            margin_impact=float(total_m),
        ))

    return SectorShockResult(
        applicable=True, sector=sector, base_intrinsic=float(base_intrinsic),
        scenarios=scenarios,
        note=("Margin impact applied as additional stage-1 growth drag — "
              "the DCF takes growth, not margin, as input."),
    )
