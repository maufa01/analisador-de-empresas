"""
Damodaran industry-benchmark loader.

Strategy:
1. If pre-cached parquet files exist under ``data/damodaran/`` (produced
   by ``scripts/load_damodaran_data.py``), read from them — fastest path.
2. Otherwise fall back to the hardcoded ``INDUSTRY_AVERAGES`` map in
   ``data/company_profiles.py`` so the UI never sees a blank benchmark.

Streamlit Cloud's outbound HTTP can be flaky and Damodaran's URLs drift
year over year — keeping the runtime path off the network and on the
local cache means the page never blocks on a wonky NYU server.

The public surface is intentionally narrow: ``get_industry_benchmarks``
returns a dict of ``{metric_key: value}`` with a stable schema regardless
of whether the data came from the parquet cache or the fallback.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.industry_mapper import get_damodaran_industry
from data.company_profiles import get_industry_averages as _hardcoded_industry_averages


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data" / "damodaran"


# Damodaran column → our normalised metric key. Damodaran ships several
# spellings ("Beta", "Average Beta", " Beta") across years — we try a
# few before giving up.
_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "betas":        ("Beta", "Average Beta", "Average Unlevered Beta",
                     "Unlevered Beta"),
    "wacc":         ("Cost of Capital", "Cost of capital",
                     "WACC"),
    "cost_of_equity": ("Cost of Equity",),
    "operating_margin": ("Operating Margin", "EBIT/Sales",
                         "Pre-tax Operating Margin"),
    "net_margin":   ("Net Margin", "Net Income/Sales"),
    "gross_margin": ("Gross Margin",),
    "ebitda_margin": ("EBITDA/Sales", "EBITDA Margin"),
    "roe":          ("ROE", "Return on Equity"),
    "roic":         ("ROIC", "Return on Invested Capital",
                     "ROIC (unadjusted)"),
    "pe_ratio":     ("PE", "Trailing PE", "Current PE"),
    "ev_ebitda":    ("EV/EBITDA", "Enterprise Value/EBITDA"),
    "ps_ratio":     ("EV/Sales", "PS"),
    "pb_ratio":     ("Price/Book", "PBV"),
    "debt_to_equity": ("Total Debt/Equity", "D/E"),
    "current_ratio": ("Current Ratio",),
    "asset_turnover": ("Sales/Capital", "Asset Turnover"),
    "interest_coverage": ("Interest coverage ratio", "Interest Coverage"),
    "growth":       ("Expected Growth in Revenues",
                     "Expected Growth in Net Income",
                     "Average Revenue Growth"),
}


def _industry_col(df: pd.DataFrame) -> Optional[str]:
    """Damodaran uses "Industry Name" in most files but the column drifts."""
    for cand in ("Industry Name", "Industry", "Sector"):
        if cand in df.columns:
            return cand
    return None


def _resolve_value(row: pd.Series, hints: tuple[str, ...]) -> Optional[float]:
    for col in row.index:
        col_str = str(col).strip()
        for hint in hints:
            if col_str.lower() == hint.lower():
                try:
                    v = float(row[col])
                    if pd.isna(v):
                        return None
                    return v
                except (TypeError, ValueError):
                    return None
    return None


def _from_parquet_cache(damodaran_industry: str) -> dict[str, Optional[float]]:
    """Read every parquet file in ``data/damodaran/`` and pluck the row
    matching ``damodaran_industry``. Missing files are skipped."""
    out: dict[str, Optional[float]] = {}
    if not _DATA_DIR.exists():
        return out
    for parquet in _DATA_DIR.glob("*.parquet"):
        try:
            df = pd.read_parquet(parquet)
        except Exception:
            continue
        col = _industry_col(df)
        if col is None:
            continue
        match = df[df[col].astype(str).str.strip() == damodaran_industry]
        if match.empty:
            continue
        row = match.iloc[0]
        for metric_key, hints in _COLUMN_HINTS.items():
            if metric_key in out and out[metric_key] is not None:
                continue
            v = _resolve_value(row, hints)
            if v is not None:
                # Damodaran ships percentages as decimals (0.412 = 41.2%);
                # our internal ratios use percentage points.
                if metric_key in {
                    "operating_margin", "net_margin", "gross_margin",
                    "ebitda_margin", "roe", "roic", "growth",
                }:
                    v = v * 100.0 if abs(v) < 5 else v
                out[metric_key] = v
    return out


# ============================================================
# Public API
# ============================================================
def get_industry_benchmarks(
    industry: Optional[str],
    *,
    sector: Optional[str] = None,
) -> dict[str, Optional[float]]:
    """
    Returns a dict of ``{metric_key: value}`` for a GICS industry name.

    Order of resolution:
      1. Parquet cache under data/damodaran/ (when present).
      2. Hardcoded ``INDUSTRY_AVERAGES`` in data/company_profiles.py
         (always available).

    Both paths return the same key schema so callers don't need to
    branch.
    """
    damodaran_industry = get_damodaran_industry(industry, sector=sector)
    cached = _from_parquet_cache(damodaran_industry)
    if cached:
        return cached
    return _hardcoded_industry_averages(sector or industry or "") or {}


def get_metric_with_context(
    metric_key: str,
    value: Optional[float],
    *,
    industry: Optional[str] = None,
    sector: Optional[str] = None,
) -> dict:
    """
    Annotate a single metric with its industry-average context.

    Returns ``{value, industry_avg, vs_industry, above_industry}`` —
    callers render the badge / pill from this dict.
    """
    benchmarks = get_industry_benchmarks(industry, sector=sector)
    industry_avg = benchmarks.get(metric_key)

    out = {
        "value":           value,
        "industry_avg":    industry_avg,
        "vs_industry":     None,
        "above_industry":  None,
    }
    if value is None or industry_avg is None or industry_avg == 0:
        return out
    out["vs_industry"]    = (value - industry_avg) / abs(industry_avg)
    out["above_industry"] = bool(value > industry_avg)
    return out
