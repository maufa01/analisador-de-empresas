"""
Hardcoded INDUSTRY_AVERAGES table (Damodaran / NYU / CFA-Institute
benchmarks). Used by ratios_grid.py and damodaran_loader.py as a
sector-level reference set.

The deprecated ``PROFILES`` / ``EXECUTIVES`` dicts (AAPL/MSFT/JPM
hardcoded) have been removed — the live FMP → yfinance chain in
:func:`analysis.data_adapter.get_company_info` and the
:class:`analysis.parallel_loader.HydratedBundle` ``fmp_profile``
field cover any ticker.

Refresh INDUSTRY_AVERAGES manually as Damodaran's tables drift
year over year.
"""
from __future__ import annotations
from typing import Optional


INDUSTRY_AVERAGES: dict[str, dict[str, float]] = {
    # ---- Tech / consumer electronics + software ----
    "Technology": {
        "gross_margin":      38.2,
        "operating_margin":  18.9,
        "ebitda_margin":     22.5,
        "net_margin":        15.6,
        "fcf_margin":        18.0,
        "roe":               32.1,
        "roa":               12.5,
        "roic":              22.3,
        "asset_turnover":    0.85,
        "current_ratio":     1.85,
        "quick_ratio":       1.55,
        "cash_ratio":        0.95,
        "debt_to_equity":    0.65,
        "debt_to_ebitda":    1.40,
        "interest_coverage": 22.0,
        "pe_ratio":          27.4,
        "forward_pe":        25.0,
        "ev_ebitda":         19.0,
        "ps_ratio":          5.20,
        "pb_ratio":          7.10,
    },
    # ---- Big banks ----
    "Financial Services": {
        "gross_margin":      None,           # Banks don't report a meaningful "gross margin"
        "operating_margin":  35.5,
        "ebitda_margin":     None,
        "net_margin":        24.0,
        "fcf_margin":        None,
        "roe":               12.0,
        "roa":               1.10,
        "roic":              8.5,
        "asset_turnover":    0.05,
        "current_ratio":     None,           # Inappropriate for a bank
        "quick_ratio":       None,
        "cash_ratio":        None,
        "debt_to_equity":    1.50,
        "debt_to_ebitda":    None,
        "interest_coverage": 4.0,
        "pe_ratio":          11.0,
        "forward_pe":        10.5,
        "ev_ebitda":         None,
        "ps_ratio":          2.40,
        "pb_ratio":          1.40,
    },
}


# ============================================================
# Public API — returns {} for unknown sectors
# ============================================================
def get_industry_averages(sector: Optional[str]) -> dict[str, Optional[float]]:
    """Industry-average ratios for a sector — empty dict if not curated."""
    if not sector:
        return {}
    return INDUSTRY_AVERAGES.get(sector, {})
