"""
Per-ticker valuation assumptions — defaults computed from the
company's own financials, with safe fall-backs to ``core/constants.py``.

A single ``Assumptions`` dataclass holds every input the valuation
pipeline needs. Three flavours are exposed:

- ``base_case``        — defaults derived from the financials
- ``bull_case``        — growth +50%, WACC −100bp, terminal +50bp
- ``bear_case``        — growth −50%, WACC +100bp, terminal −50bp
- ``apply_preset``     — convenience switcher
- ``modified_fields``  — diff vs base used by the UI for "modified" dots

Inputs are loose: any missing field falls back to the constants and the
caller can inspect ``warnings`` to see which defaults were generic.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, replace
from typing import Optional

import numpy as np
import pandas as pd

from analysis.ratios import _get, effective_tax_rate
from core.constants import (
    DCF_DEFAULTS, DEFAULT_WACC_PARAMS, MONTE_CARLO_DEFAULTS,
)


# ============================================================
# Dataclass
# ============================================================
@dataclass
class Assumptions:
    """Every input the valuation pipeline needs, in a single struct."""
    # ---- WACC ----
    beta: float = DEFAULT_WACC_PARAMS["beta"]
    risk_free: float = DEFAULT_WACC_PARAMS["risk_free_rate"]
    equity_risk_premium: float = DEFAULT_WACC_PARAMS["market_risk_premium"]
    cost_of_debt: float = DEFAULT_WACC_PARAMS["cost_of_debt"]
    tax_rate: float = DEFAULT_WACC_PARAMS["tax_rate"]

    # ---- Capital structure ----
    weight_equity: float = DEFAULT_WACC_PARAMS["weight_equity"]

    # ---- DCF projection ----
    stage1_years: int = int(DCF_DEFAULTS["stage1_years"])
    stage2_years: int = int(DCF_DEFAULTS["stage2_years"])
    terminal_growth: float = float(DCF_DEFAULTS["terminal_growth"])
    override_growth: Optional[float] = None     # None ⇒ use historical CAGR

    # ---- Monte Carlo ----
    mc_n_simulations: int = int(MONTE_CARLO_DEFAULTS["n_simulations"])
    mc_rev_growth_std: float = float(MONTE_CARLO_DEFAULTS["rev_growth_std_floor"])
    mc_wacc_std: float = float(MONTE_CARLO_DEFAULTS["wacc_std"])
    mc_terminal_low: float = float(MONTE_CARLO_DEFAULTS["terminal_growth_low"])
    mc_terminal_high: float = float(MONTE_CARLO_DEFAULTS["terminal_growth_high"])

    # ---- Provenance ----
    warnings: list[str] = field(default_factory=list)

    @property
    def weight_debt(self) -> float:
        return 1.0 - self.weight_equity

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("warnings", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Assumptions":
        valid = {k: v for k, v in d.items()
                 if k in cls.__dataclass_fields__ and k != "warnings"}
        return cls(**valid)


# ============================================================
# Internal helpers
# ============================================================
def _historical_cost_of_debt(
    income: pd.DataFrame, balance: pd.DataFrame
) -> Optional[float]:
    """Interest expense / average total debt over the last 3 years."""
    interest = _get(income, "interest_expense")
    debt = _get(balance, "total_debt")
    if interest is None or debt is None:
        return None
    df = pd.concat([interest, debt], axis=1).dropna().tail(3)
    df.columns = ["i", "d"]
    df = df[df["d"] > 0]
    if df.empty:
        return None
    return float((df["i"] / df["d"]).mean())


def _market_or_book_capital_structure(
    balance: pd.DataFrame,
    market_cap: Optional[float] = None,
) -> Optional[float]:
    """
    Returns the equity weight (E/(E+D)) using market cap if given,
    else book equity. Returns None if neither is computable.
    """
    debt_s = _get(balance, "total_debt")
    if debt_s is None or debt_s.dropna().empty:
        return None
    debt = float(debt_s.dropna().iloc[-1])

    if market_cap and market_cap > 0:
        equity = float(market_cap)
    else:
        eq_s = _get(balance, "total_equity")
        if eq_s is None or eq_s.dropna().empty:
            return None
        equity = float(eq_s.dropna().iloc[-1])
        if equity <= 0:
            return None

    total = equity + debt
    if total <= 0:
        return None
    return float(equity / total)


def _historical_revenue_growth_std(income: pd.DataFrame) -> Optional[float]:
    """Std of YoY revenue growth across available history."""
    rev = _get(income, "revenue")
    if rev is None:
        return None
    s = rev.dropna()
    if len(s) < 3:
        return None
    growth = s.pct_change().dropna()
    if len(growth) < 2:
        return None
    return float(growth.std(ddof=1))


def _historical_terminal_band(income: pd.DataFrame, cash: pd.DataFrame) -> tuple[float, float]:
    """
    Conservative terminal-growth band: clamped between the constants and
    the realised mean revenue growth ± its std.

    Returns (low, high) in decimal form.
    """
    base_low = float(MONTE_CARLO_DEFAULTS["terminal_growth_low"])
    base_high = float(MONTE_CARLO_DEFAULTS["terminal_growth_high"])

    rev = _get(income, "revenue")
    if rev is None or rev.dropna().empty:
        return base_low, base_high

    growth = rev.dropna().pct_change().dropna()
    if growth.empty:
        return base_low, base_high

    mean = float(growth.mean())
    std = float(growth.std(ddof=1)) if len(growth) > 1 else 0.0
    # Pull toward 0–4% but allow some company-specific drift
    lo = float(np.clip(min(base_low, mean - std / 2), 0.0, 0.04))
    hi = float(np.clip(max(base_high, mean + std / 2), lo + 0.005, 0.06))
    return lo, hi


# ============================================================
# Public API — build Assumptions from financials
# ============================================================
def calculate_default_assumptions(
    *,
    income: Optional[pd.DataFrame] = None,
    balance: Optional[pd.DataFrame] = None,
    cash: Optional[pd.DataFrame] = None,
    beta_override: Optional[float] = None,
    risk_free_override: Optional[float] = None,
    market_cap: Optional[float] = None,
) -> Assumptions:
    """
    Compute base-case assumptions from a company's financials.

    Falls back to ``core/constants`` defaults for anything that can't be
    derived. Records human-readable notes in ``Assumptions.warnings`` so
    the UI can flag generic vs computed values.
    """
    a = Assumptions()
    if beta_override is not None:
        a.beta = float(beta_override)
    if risk_free_override is not None:
        a.risk_free = float(risk_free_override)

    # ---- Cost of debt + tax (from income / balance) ----
    if income is not None and balance is not None:
        rd = _historical_cost_of_debt(income, balance)
        if rd is not None and 0.001 < rd < 0.30:
            a.cost_of_debt = rd
        else:
            a.warnings.append("cost_of_debt: using generic default")

        try:
            a.tax_rate = float(effective_tax_rate(income))
        except Exception:
            a.warnings.append("tax_rate: using generic default")

        # ---- Capital structure ----
        we = _market_or_book_capital_structure(balance, market_cap=market_cap)
        if we is not None and 0.05 <= we <= 0.99:
            a.weight_equity = we
            if market_cap is None:
                a.warnings.append(
                    "weight_equity: using book equity (no market cap supplied)"
                )
        else:
            a.warnings.append("weight_equity: using generic 70/30 default")
    else:
        a.warnings.append(
            "cost_of_debt / tax / weights: no financials supplied, using generics"
        )

    # ---- Monte Carlo: stochasticity from the data ----
    if income is not None:
        rev_std = _historical_revenue_growth_std(income)
        if rev_std is not None:
            # Floor at the constant so a perfectly-stable revenue series still
            # produces *some* dispersion in the simulations.
            a.mc_rev_growth_std = max(
                rev_std, float(MONTE_CARLO_DEFAULTS["rev_growth_std_floor"])
            )

        if cash is not None:
            lo, hi = _historical_terminal_band(income, cash)
            a.mc_terminal_low = lo
            a.mc_terminal_high = hi

    return a


# ============================================================
# Presets
# ============================================================
PRESETS: tuple[str, ...] = ("Base case", "Bull case", "Bear case", "Custom")


def apply_preset(base: Assumptions, preset: str) -> Assumptions:
    """
    Returns a new ``Assumptions`` with the preset's transformation applied.

    - ``Base case``: identity (returns a fresh copy of base)
    - ``Bull case``: growth ×1.5 (capped), WACC components shifted to
      lower the WACC ~100bp, terminal +50bp
    - ``Bear case``: mirror of Bull case
    - ``Custom``: identity (the caller will overlay user edits afterwards)
    """
    if preset in ("Base case", "Custom"):
        return replace(base, warnings=list(base.warnings))

    if preset == "Bull case":
        return replace(
            base,
            warnings=list(base.warnings),
            override_growth=(
                base.override_growth * 1.5
                if base.override_growth is not None else None
            ),
            risk_free=max(0.0, base.risk_free - 0.005),
            equity_risk_premium=max(0.01, base.equity_risk_premium - 0.005),
            terminal_growth=min(
                float(DCF_DEFAULTS["growth_cap_upper"]),
                base.terminal_growth + 0.005,
            ),
        )

    if preset == "Bear case":
        return replace(
            base,
            warnings=list(base.warnings),
            override_growth=(
                base.override_growth * 0.5
                if base.override_growth is not None else None
            ),
            risk_free=base.risk_free + 0.005,
            equity_risk_premium=base.equity_risk_premium + 0.005,
            terminal_growth=max(0.0, base.terminal_growth - 0.005),
        )

    raise ValueError(f"Unknown preset: {preset!r}")


# ============================================================
# Diff for the UI's "modified" dots
# ============================================================
def modified_fields(
    current: Assumptions,
    baseline: Assumptions,
    *,
    tol: float = 1e-6,
) -> set[str]:
    """Return the names of fields that differ from ``baseline``."""
    out: set[str] = set()
    for k in current.__dataclass_fields__:
        if k == "warnings":
            continue
        cv = getattr(current, k)
        bv = getattr(baseline, k)
        if isinstance(cv, float) and isinstance(bv, float):
            if abs(cv - bv) > tol:
                out.add(k)
        elif cv != bv:
            out.add(k)
    return out
