"""
Historical stress scenarios — replay a real past crisis window against
the current holdings.

Each scenario is (start, end) plus a description. We refetch adjusted
close prices for that window and compute per-ticker change, max
drawdown, dollar impact, plus a portfolio-path series. Tickers that
weren't listed during the window are skipped silently — the result
still reports impact on whatever subset of holdings did have data.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional

import pandas as pd

from .data_prep import fetch_window_prices


@dataclass(frozen=True)
class HistoricalScenario:
    name: str
    start: date
    end: date
    description: str


HISTORICAL_SCENARIOS: tuple[HistoricalScenario, ...] = (
    HistoricalScenario(
        "2008 Financial Crisis", date(2008, 9, 1), date(2009, 3, 9),
        "Lehman to S&P trough — banks devastated, broad-market drawdown.",
    ),
    HistoricalScenario(
        "2020 COVID Crash", date(2020, 2, 19), date(2020, 3, 23),
        "Pandemic shock — 34% S&P drawdown in 33 days.",
    ),
    HistoricalScenario(
        "2022 Rate Hike Cycle", date(2022, 1, 3), date(2022, 10, 12),
        "Fed hikes. Tech / growth crushed, bonds also fell.",
    ),
    HistoricalScenario(
        "2000 Dotcom Crash", date(2000, 3, 24), date(2002, 10, 9),
        "Tech bubble burst. NASDAQ -78% over 30 months.",
    ),
    HistoricalScenario(
        "2018 Q4 Selloff", date(2018, 9, 20), date(2018, 12, 24),
        "Hawkish Fed + trade-war fears — ~20% drawdown.",
    ),
    HistoricalScenario(
        "2011 Debt-Ceiling", date(2011, 7, 22), date(2011, 10, 3),
        "US downgrade + Eurozone fears.",
    ),
    HistoricalScenario(
        "2015-16 China Slowdown", date(2015, 8, 10), date(2016, 2, 11),
        "China + oil crash — Energy decimated.",
    ),
    HistoricalScenario(
        "2023 SVB Banking", date(2023, 3, 8), date(2023, 3, 24),
        "SVB collapse — regional banks hit hardest.",
    ),
)


def run_scenario(
    scenario: HistoricalScenario,
    holdings_dollars: Mapping[str, float],
    portfolio_value: float,
    *,
    benchmark: Optional[str] = "SPY",
) -> dict:
    """Replay one historical window against the current holdings."""
    if portfolio_value <= 0:
        return {"scenario": scenario.name, "error": "Portfolio value must be > 0"}

    tickers = list(holdings_dollars.keys())
    fetch_list = tuple(tickers + [benchmark]) if benchmark else tuple(tickers)
    prices = fetch_window_prices(fetch_list, scenario.start, scenario.end)
    if prices is None or prices.empty:
        return {"scenario": scenario.name, "error": "No price data for window"}

    weights = {t: v / portfolio_value for t, v in holdings_dollars.items()}

    ticker_results: dict[str, dict] = {}
    for t in tickers:
        if t not in prices.columns:
            continue
        s = prices[t].dropna()
        if len(s) < 2:
            continue
        start_p, end_p = float(s.iloc[0]), float(s.iloc[-1])
        if start_p <= 0:
            continue
        cum_max = s.expanding().max()
        max_dd = float(((s - cum_max) / cum_max).min() * 100.0)
        pct = (end_p / start_p - 1.0) * 100.0
        impact = holdings_dollars[t] * (end_p / start_p - 1.0)
        ticker_results[t] = {
            "weight": weights.get(t, 0.0),
            "start_price": start_p,
            "end_price": end_p,
            "pct_change": pct,
            "max_drawdown": max_dd,
            "dollar_impact": impact,
        }

    if not ticker_results:
        return {"scenario": scenario.name, "error": "No holdings had data in window"}

    total_dollar = sum(r["dollar_impact"] for r in ticker_results.values())
    pct_change = (total_dollar / portfolio_value) * 100.0

    valid = [t for t in tickers if t in ticker_results]
    if valid:
        norm = prices[valid] / prices[valid].iloc[0]
        w_series = pd.Series({t: weights.get(t, 0.0) for t in valid})
        if w_series.sum() > 0:
            w_series = w_series / w_series.sum()
        portfolio_path = (norm * w_series).sum(axis=1) - 1.0
        cum_max = (1 + portfolio_path).expanding().max()
        port_dd = float(((1 + portfolio_path - cum_max) / cum_max).min() * 100.0)
    else:
        portfolio_path = pd.Series(dtype=float)
        port_dd = float("nan")

    bench_pct = None
    if benchmark and benchmark in prices.columns:
        b = prices[benchmark].dropna()
        if len(b) >= 2 and float(b.iloc[0]) > 0:
            bench_pct = (float(b.iloc[-1] / b.iloc[0]) - 1.0) * 100.0

    return {
        "scenario": scenario.name,
        "description": scenario.description,
        "start": scenario.start,
        "end": scenario.end,
        "portfolio_pct": pct_change,
        "portfolio_dollar": total_dollar,
        "new_value": portfolio_value + total_dollar,
        "portfolio_max_dd": port_dd,
        "benchmark_pct": bench_pct,
        "alpha_vs_benchmark": (pct_change - bench_pct) if bench_pct is not None else None,
        "ticker_results": ticker_results,
        "portfolio_path": portfolio_path,
    }


def run_all(
    holdings_dollars: Mapping[str, float],
    portfolio_value: float,
    *,
    benchmark: Optional[str] = "SPY",
) -> list[dict]:
    return [run_scenario(s, holdings_dollars, portfolio_value, benchmark=benchmark)
            for s in HISTORICAL_SCENARIOS]
