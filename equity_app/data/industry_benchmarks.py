"""
Sector-level ratio benchmarks — Damodaran-style averages for the 11
GICS sectors. Hardcoded so we don't depend on a network call to give
each ratio context.

Each sector dict is a flat ``{ratio_name: float}`` map. ``get_benchmark``
returns ``None`` when the sector or ratio is unknown — callers should
gracefully omit the "vs sector" line in that case.

Refresh ~once a year against Damodaran's published industry data set:
https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html

Conventions:
    - Margins / yields / returns expressed as decimals (0.20 = 20%).
    - Ratios (D/E, current ratio, P/E…) expressed as plain multipliers.
    - Days metrics (DSO / DIO / DPO / CCC) expressed in days.
"""
from __future__ import annotations
from typing import Optional


INDUSTRY_BENCHMARKS: dict[str, dict[str, float]] = {
    "Technology": {
        "gross_margin":      0.55,
        "operating_margin":  0.20,
        "net_margin":        0.18,
        "fcf_margin":        0.20,
        "roe":               0.20,
        "roa":               0.10,
        "roic":              0.15,
        "roce":              0.15,
        "current_ratio":     2.5,
        "quick_ratio":       2.2,
        "debt_to_equity":    0.40,
        "debt_to_assets":    0.20,
        "interest_coverage": 12.0,
        "asset_turnover":    0.65,
        "pe_ratio":          28.0,
        "ps_ratio":          5.5,
        "pb_ratio":          7.0,
        "ev_to_ebitda":      18.0,
        "ev_to_revenue":     5.0,
        "fcf_yield":         0.035,
    },
    "Healthcare": {
        "gross_margin":      0.45,
        "operating_margin":  0.15,
        "net_margin":        0.10,
        "fcf_margin":        0.12,
        "roe":               0.15,
        "roa":               0.06,
        "roic":              0.12,
        "roce":              0.11,
        "current_ratio":     2.0,
        "quick_ratio":       1.6,
        "debt_to_equity":    0.60,
        "debt_to_assets":    0.27,
        "interest_coverage": 8.0,
        "asset_turnover":    0.55,
        "pe_ratio":          22.0,
        "ps_ratio":          3.0,
        "pb_ratio":          3.5,
        "ev_to_ebitda":      14.0,
        "ev_to_revenue":     2.5,
        "fcf_yield":         0.045,
    },
    "Consumer Defensive": {
        "gross_margin":      0.35,
        "operating_margin":  0.12,
        "net_margin":        0.08,
        "fcf_margin":        0.09,
        "roe":               0.18,
        "roa":               0.07,
        "roic":              0.14,
        "roce":              0.13,
        "current_ratio":     1.2,
        "quick_ratio":       0.7,
        "debt_to_equity":    0.70,
        "debt_to_assets":    0.30,
        "interest_coverage": 9.0,
        "asset_turnover":    0.85,
        "pe_ratio":          22.0,
        "ps_ratio":          1.5,
        "pb_ratio":          4.0,
        "ev_to_ebitda":      14.0,
        "ev_to_revenue":     1.7,
        "fcf_yield":         0.042,
    },
    "Consumer Cyclical": {
        "gross_margin":      0.32,
        "operating_margin":  0.08,
        "net_margin":        0.06,
        "fcf_margin":        0.06,
        "roe":               0.15,
        "roa":               0.06,
        "roic":              0.12,
        "roce":              0.11,
        "current_ratio":     1.4,
        "quick_ratio":       0.7,
        "debt_to_equity":    0.80,
        "debt_to_assets":    0.32,
        "interest_coverage": 7.0,
        "asset_turnover":    1.10,
        "pe_ratio":          20.0,
        "ps_ratio":          1.2,
        "pb_ratio":          3.5,
        "ev_to_ebitda":      12.0,
        "ev_to_revenue":     1.4,
        "fcf_yield":         0.045,
    },
    "Energy": {
        "gross_margin":      0.25,
        "operating_margin":  0.10,
        "net_margin":        0.07,
        "fcf_margin":        0.08,
        "roe":               0.12,
        "roa":               0.05,
        "roic":              0.08,
        "roce":              0.08,
        "current_ratio":     1.2,
        "quick_ratio":       0.9,
        "debt_to_equity":    0.50,
        "debt_to_assets":    0.25,
        "interest_coverage": 6.0,
        "asset_turnover":    0.70,
        "pe_ratio":          14.0,
        "ps_ratio":          1.0,
        "pb_ratio":          1.6,
        "ev_to_ebitda":      7.0,
        "ev_to_revenue":     1.2,
        "fcf_yield":         0.07,
    },
    "Financial Services": {
        "operating_margin":  0.30,
        "net_margin":        0.20,
        "roe":               0.12,
        "roa":               0.012,
        "debt_to_equity":    4.5,
        "pe_ratio":          14.0,
        "pb_ratio":          1.3,
        "ps_ratio":          3.0,
    },
    "Industrials": {
        "gross_margin":      0.28,
        "operating_margin":  0.10,
        "net_margin":        0.07,
        "fcf_margin":        0.07,
        "roe":               0.16,
        "roa":               0.06,
        "roic":              0.11,
        "roce":              0.10,
        "current_ratio":     1.6,
        "quick_ratio":       1.0,
        "debt_to_equity":    0.70,
        "debt_to_assets":    0.30,
        "interest_coverage": 7.0,
        "asset_turnover":    0.85,
        "pe_ratio":          20.0,
        "ps_ratio":          1.4,
        "pb_ratio":          3.0,
        "ev_to_ebitda":      12.0,
        "ev_to_revenue":     1.6,
        "fcf_yield":         0.045,
    },
    "Basic Materials": {
        "gross_margin":      0.25,
        "operating_margin":  0.10,
        "net_margin":        0.06,
        "fcf_margin":        0.05,
        "roe":               0.12,
        "roa":               0.05,
        "roic":              0.09,
        "roce":              0.09,
        "current_ratio":     1.7,
        "quick_ratio":       1.0,
        "debt_to_equity":    0.60,
        "debt_to_assets":    0.27,
        "interest_coverage": 6.0,
        "asset_turnover":    0.85,
        "pe_ratio":          17.0,
        "ps_ratio":          1.3,
        "pb_ratio":          2.0,
        "ev_to_ebitda":      9.0,
        "ev_to_revenue":     1.4,
        "fcf_yield":         0.05,
    },
    "Real Estate": {
        "gross_margin":      0.65,
        "operating_margin":  0.30,
        "net_margin":        0.20,
        "fcf_margin":        0.18,
        "roe":               0.10,
        "roa":               0.04,
        "roic":              0.07,
        "roce":              0.06,
        "current_ratio":     1.0,
        "debt_to_equity":    1.50,
        "debt_to_assets":    0.55,
        "interest_coverage": 3.5,
        "pe_ratio":          25.0,
        "ps_ratio":          5.0,
        "pb_ratio":          1.8,
        "ev_to_ebitda":      18.0,
        "fcf_yield":         0.045,
    },
    "Utilities": {
        "gross_margin":      0.40,
        "operating_margin":  0.18,
        "net_margin":        0.10,
        "fcf_margin":        0.06,
        "roe":               0.10,
        "roa":               0.03,
        "roic":              0.07,
        "roce":              0.07,
        "current_ratio":     0.9,
        "debt_to_equity":    1.40,
        "debt_to_assets":    0.50,
        "interest_coverage": 3.5,
        "pe_ratio":          18.0,
        "ps_ratio":          1.8,
        "pb_ratio":          1.7,
        "ev_to_ebitda":      11.0,
        "fcf_yield":         0.04,
    },
    "Communication Services": {
        "gross_margin":      0.50,
        "operating_margin":  0.20,
        "net_margin":        0.15,
        "fcf_margin":        0.18,
        "roe":               0.18,
        "roa":               0.08,
        "roic":              0.13,
        "roce":              0.12,
        "current_ratio":     1.5,
        "quick_ratio":       1.3,
        "debt_to_equity":    0.60,
        "debt_to_assets":    0.27,
        "interest_coverage": 9.0,
        "asset_turnover":    0.55,
        "pe_ratio":          24.0,
        "ps_ratio":          3.5,
        "pb_ratio":          3.5,
        "ev_to_ebitda":      13.0,
        "ev_to_revenue":     3.5,
        "fcf_yield":         0.045,
    },
}


# yfinance / Finnhub label variants — map them to the canonical keys.
_SECTOR_ALIASES: dict[str, str] = {
    "Consumer Staples":          "Consumer Defensive",
    "Consumer Discretionary":    "Consumer Cyclical",
    "Materials":                 "Basic Materials",
    "Telecom":                   "Communication Services",
    "Telecommunications":        "Communication Services",
    "Information Technology":    "Technology",
    "Financials":                "Financial Services",
}


def normalise_sector(sector: Optional[str]) -> Optional[str]:
    """Map common provider-label variants to one of the canonical sector names."""
    if not sector:
        return None
    s = sector.strip()
    if s in INDUSTRY_BENCHMARKS:
        return s
    return _SECTOR_ALIASES.get(s, s)


def get_benchmark(sector: Optional[str], ratio_name: str) -> Optional[float]:
    """
    Returns the sector benchmark value for ``ratio_name`` or None when
    either the sector or the ratio isn't covered.

    Margins/yields/returns are decimals; ratios are unit-less multipliers.
    """
    canonical = normalise_sector(sector)
    if not canonical:
        return None
    sector_data = INDUSTRY_BENCHMARKS.get(canonical, {})
    val = sector_data.get(ratio_name)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def list_sectors() -> list[str]:
    return list(INDUSTRY_BENCHMARKS.keys())
