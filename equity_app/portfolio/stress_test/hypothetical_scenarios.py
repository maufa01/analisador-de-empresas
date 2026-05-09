"""
Forward-looking macro shocks. Each scenario is a (market_shock,
{sector_key: shock}) pair, applied per-holding via that holding's
sector classification × CAPM beta.

Per-ticker rule:
- if a sector-specific shock matches the holding's sector AND its
  magnitude exceeds the broad-market × beta term, use the sector shock
- otherwise fall back to market_shock × beta

This matches the heuristic in the spec — sector overlays kick in only
when they are MORE severe than the generic market move, leaving lower-
correlated names untouched.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping


# Map yfinance / GICS sector strings to scenario keys.
_SECTOR_KEY: dict[str, str] = {
    "Technology": "tech",
    "Communication Services": "tech",
    "Consumer Cyclical": "discretionary",
    "Consumer Discretionary": "discretionary",
    "Financial Services": "financials",
    "Financials": "financials",
    "Healthcare": "healthcare",
    "Health Care": "healthcare",
    "Consumer Defensive": "staples",
    "Consumer Staples": "staples",
    "Industrials": "industrials",
    "Energy": "energy",
    "Utilities": "utilities",
    "Real Estate": "real_estate",
    "Basic Materials": "materials",
    "Materials": "materials",
}


@dataclass(frozen=True)
class HypotheticalScenario:
    name: str
    description: str
    market: float                          # broad equity shock, e.g. -0.30
    sectors: dict[str, float] = field(default_factory=dict)


HYPOTHETICAL_SCENARIOS: tuple[HypotheticalScenario, ...] = (
    HypotheticalScenario(
        "Mild Recession",
        "GDP -1%, unemployment 6%, equity -15%.",
        market=-0.15,
        sectors={"tech": -0.20, "financials": -0.18, "discretionary": -0.20,
                 "staples": -0.05, "healthcare": -0.08, "utilities": +0.02},
    ),
    HypotheticalScenario(
        "Severe Recession (2008-style)",
        "GDP -3%, unemployment 10%, equity -40%.",
        market=-0.40,
        sectors={"tech": -0.45, "financials": -0.55, "discretionary": -0.45,
                 "staples": -0.15, "healthcare": -0.20, "utilities": -0.10,
                 "energy": -0.50},
    ),
    HypotheticalScenario(
        "High Inflation Persistent",
        "CPI 6%+, Fed funds 7%, growth crushed.",
        market=-0.25,
        sectors={"tech": -0.35, "real_estate": -0.30, "utilities": -0.15,
                 "staples": -0.10, "energy": +0.20, "financials": +0.05},
    ),
    HypotheticalScenario(
        "Tech Bubble Burst",
        "NASDAQ -50%, rest -25% (2000-style).",
        market=-0.25,
        sectors={"tech": -0.50, "discretionary": -0.30, "financials": -0.15,
                 "staples": -0.10, "healthcare": -0.15, "utilities": -0.05,
                 "energy": -0.10},
    ),
    HypotheticalScenario(
        "Geopolitical Shock",
        "Major conflict, oil +50%, flight to safety.",
        market=-0.20,
        sectors={"energy": +0.40, "tech": -0.25, "discretionary": -0.30,
                 "financials": -0.20, "industrials": +0.10},
    ),
    HypotheticalScenario(
        "Soft Landing — Rate Cuts",
        "Fed cuts to 2%, growth rebounds.",
        market=+0.20,
        sectors={"tech": +0.30, "real_estate": +0.25, "discretionary": +0.25,
                 "utilities": +0.15, "financials": +0.05},
    ),
    HypotheticalScenario(
        "Stagflation",
        "High inflation + low growth.",
        market=-0.30,
        sectors={"tech": -0.40, "discretionary": -0.35, "staples": -0.15,
                 "real_estate": -0.30, "energy": +0.30, "utilities": -0.10},
    ),
)


def _ticker_impact(beta: float, sector: str | None,
                   scenario: HypotheticalScenario) -> float:
    """Per-ticker expected return under scenario."""
    market_part = scenario.market * (beta if beta else 1.0)
    if not sector:
        return market_part
    key = _SECTOR_KEY.get(sector)
    if not key or key not in scenario.sectors:
        return market_part
    sector_shock = scenario.sectors[key]
    return sector_shock if abs(sector_shock) > abs(market_part) else market_part


def run_scenario(
    scenario: HypotheticalScenario,
    holdings: Mapping[str, dict],          # {ticker: {weight, sector, beta}}
    portfolio_value: float,
) -> dict:
    impacts: dict[str, dict] = {}
    total_dollar = 0.0
    for t, info in holdings.items():
        weight = float(info.get("weight", 0.0))
        sector = info.get("sector")
        try:
            beta = float(info.get("beta", 1.0) or 1.0)
        except (TypeError, ValueError):
            beta = 1.0
        pct = _ticker_impact(beta, sector, scenario)
        position_value = weight * portfolio_value
        dollar = position_value * pct
        impacts[t] = {
            "weight": weight,
            "sector": sector or "—",
            "beta": beta,
            "pct_change": pct * 100.0,
            "dollar_impact": dollar,
        }
        total_dollar += dollar

    return {
        "scenario": scenario.name,
        "description": scenario.description,
        "market_shock": scenario.market,
        "sector_shocks": dict(scenario.sectors),
        "portfolio_pct": ((total_dollar / portfolio_value) * 100.0
                          if portfolio_value > 0 else 0.0),
        "portfolio_dollar": total_dollar,
        "new_value": portfolio_value + total_dollar,
        "ticker_impacts": impacts,
    }


def run_all(holdings: Mapping[str, dict], portfolio_value: float) -> list[dict]:
    return [run_scenario(s, holdings, portfolio_value)
            for s in HYPOTHETICAL_SCENARIOS]


def run_custom(
    holdings: Mapping[str, dict],
    portfolio_value: float,
    *,
    market: float,
    sectors: dict[str, float] | None = None,
) -> dict:
    custom = HypotheticalScenario(
        name="Custom",
        description=f"Market {market*100:+.1f}%",
        market=market,
        sectors=dict(sectors or {}),
    )
    return run_scenario(custom, holdings, portfolio_value)
