"""
Compare a ticker's KPIs against sector benchmarks (Damodaran-style).

The sector benchmark data lives in :mod:`data.industry_benchmarks`. This
module is the user-facing API that:
- maps human ratio names ("Gross Margin %") to benchmark keys
  ("gross_margin")
- normalises percentage units (UI carries 25.5 ⇒ 25.5%; benchmarks
  store 0.255)
- classifies position into 5 buckets and assigns a colour
- carries an interpretation string the UI can render verbatim
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from data.industry_benchmarks import get_benchmark


Position = Literal["far_above", "above", "in_line", "below", "far_below"]


# ============================================================
# Display name → benchmark key
# ============================================================
RATIO_TO_BENCHMARK: dict[str, str] = {
    "Gross Margin %":       "gross_margin",
    "Operating Margin %":   "operating_margin",
    "Net Margin %":         "net_margin",
    "FCF Margin %":         "fcf_margin",
    "ROE %":                "roe",
    "ROA %":                "roa",
    "ROIC %":               "roic",
    "ROCE %":               "roce",
    "Current Ratio":        "current_ratio",
    "Quick Ratio":          "quick_ratio",
    "Debt/Equity":          "debt_to_equity",
    "Debt/Assets":          "debt_to_assets",
    "Interest Coverage":    "interest_coverage",
    "Asset Turnover":       "asset_turnover",
    "P/E":                  "pe_ratio",
    "P/S":                  "ps_ratio",
    "P/B":                  "pb_ratio",
    "EV/EBITDA":            "ev_to_ebitda",
    "EV/Revenue":           "ev_to_revenue",
    "FCF Yield":            "fcf_yield",
}


# ============================================================
# Ratio direction — higher is better, or lower is better?
# ============================================================
HIGHER_IS_BETTER: dict[str, bool] = {
    "gross_margin": True, "operating_margin": True, "net_margin": True,
    "fcf_margin": True, "roe": True, "roa": True, "roic": True, "roce": True,
    "current_ratio": True, "quick_ratio": True, "interest_coverage": True,
    "asset_turnover": True, "fcf_yield": True,
    "debt_to_equity": False, "debt_to_assets": False,
    "pe_ratio": False, "ps_ratio": False, "pb_ratio": False,
    "ev_to_ebitda": False, "ev_to_revenue": False,
}


@dataclass
class BenchmarkComparison:
    ratio_name: str                    # display name (e.g. "ROIC %")
    value: float                       # ticker's value (display units)
    sector: str
    benchmark_value: Optional[float]   # benchmark in display units
    position: Position
    gap: Optional[float]               # value - benchmark, display units
    gap_pct: Optional[float]           # (value - benchmark) / |benchmark|
    interpretation: str
    color: str                         # hex, for UI
    higher_is_better: bool


# ============================================================
# Internals
# ============================================================
def _classify_value_direction(value: float, benchmark: float) -> Position:
    """Bucket VALUE direction (not performance quality). Quality is
    computed separately via :func:`_is_favorable`."""
    if benchmark == 0:
        return "in_line"
    pct_diff = (value - benchmark) / abs(benchmark)
    if pct_diff > 0.30:
        return "far_above"
    if pct_diff > 0.10:
        return "above"
    if pct_diff > -0.10:
        return "in_line"
    if pct_diff > -0.30:
        return "below"
    return "far_below"


def _is_favorable(pos: Position, higher_is_better: bool) -> Optional[bool]:
    """Is this value direction good for the company? None = neutral."""
    if pos == "in_line":
        return None
    is_above = pos in ("above", "far_above")
    return is_above if higher_is_better else (not is_above)


def _color_for(pos: Position, higher_is_better: bool) -> str:
    """Colour by performance quality, not raw direction.
    A high D/E that's far above sector → red (bad), not green.
    """
    fav = _is_favorable(pos, higher_is_better)
    if fav is None:
        return "#C9A961"
    if pos in ("far_above", "far_below"):
        return "#10B981" if fav else "#DC2626"
    return "#34D399" if fav else "#B87333"


def _descriptor(pos: Position) -> str:
    return {
        "far_above": "significantly above",
        "above":     "above",
        "in_line":   "in line with",
        "below":     "below",
        "far_below": "significantly below",
    }[pos]


def _quality_glyph(pos: Position, higher_is_better: bool) -> str:
    fav = _is_favorable(pos, higher_is_better)
    if fav is None:
        return "≈"
    return "✓" if fav else "✗"


def _interpretation(value: float, benchmark: float,
                    pos: Position, higher_is_better: bool) -> str:
    if pos == "in_line":
        return f"In line with sector ({benchmark:.2f})"
    diff = value - benchmark
    glyph = _quality_glyph(pos, higher_is_better)
    desc = _descriptor(pos)
    return f"{glyph} {desc} sector avg {benchmark:.2f} ({diff:+.2f})"


# ============================================================
# Public API
# ============================================================
def compare_to_sector(
    ratio_name: str,
    value: Optional[float],
    sector: Optional[str],
) -> Optional[BenchmarkComparison]:
    """Compare a single ratio value against the sector benchmark.

    Returns None if any input is missing or the benchmark is unknown.
    Output values are in DISPLAY UNITS — for "ROIC %" with a value of
    18.5 (meaning 18.5%), benchmark_value comes back as 15.0 (also %).
    """
    if value is None or sector is None:
        return None
    try:
        if not np.isfinite(float(value)):
            return None
    except (TypeError, ValueError):
        return None

    bench_key = RATIO_TO_BENCHMARK.get(ratio_name)
    if bench_key is None:
        return None

    benchmark_decimal = get_benchmark(sector, bench_key)
    if benchmark_decimal is None:
        return None

    # If the display name carries "%", value is already in % form
    # (e.g. 25.5 = 25.5%). Benchmarks store decimals (0.255).
    is_pct_ratio = "%" in ratio_name
    value_decimal = (value / 100.0) if is_pct_ratio else value

    higher_better = HIGHER_IS_BETTER.get(bench_key, True)
    position = _classify_value_direction(value_decimal, benchmark_decimal)
    color = _color_for(position, higher_better)

    gap_decimal = value_decimal - benchmark_decimal
    gap_pct = (gap_decimal / abs(benchmark_decimal)
               if benchmark_decimal != 0 else None)

    bench_display = benchmark_decimal * 100.0 if is_pct_ratio else benchmark_decimal
    gap_display = gap_decimal * 100.0 if is_pct_ratio else gap_decimal

    interp = _interpretation(
        value_decimal * 100.0 if is_pct_ratio else value_decimal,
        bench_display,
        position, higher_better,
    )

    return BenchmarkComparison(
        ratio_name=ratio_name,
        value=value,
        sector=sector,
        benchmark_value=bench_display,
        position=position,
        gap=gap_display,
        gap_pct=gap_pct,
        interpretation=interp,
        color=color,
        higher_is_better=higher_better,
    )


def batch_compare(
    ratios: dict[str, float],
    sector: Optional[str],
) -> dict[str, BenchmarkComparison]:
    """Compare many ratios at once. Skips ones with no benchmark."""
    out: dict[str, BenchmarkComparison] = {}
    for name, value in ratios.items():
        cmp = compare_to_sector(name, value, sector)
        if cmp is not None:
            out[name] = cmp
    return out
