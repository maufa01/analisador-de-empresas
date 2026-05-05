"""
ETF holdings analysis — which ETFs hold this ticker, with classification
into broad index / sector / thematic.

Why it matters: a name held by SPY / VOO has structural buying flows
that decouple from fundamentals. A name held by ARKK / ROBO is
trend-driven and gets violently re-rated on flows. Sector-ETF density
tells you how much of the float is forced-selling on sector rotations.

Source: ``data.fmp_extras.fetch_etf_holders``. Empty / no key → result
dataclass with ``available=False``.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ============================================================
# ETF taxonomy — keep these tight. Better to mis-classify a few
# than to inflate the "thematic" bucket with anything that vaguely
# matches a fad keyword.
# ============================================================
_BROAD_INDEX_ETFS = {
    "SPY", "VOO", "IVV", "QQQ", "VTI", "DIA", "IWM",
    "VXF", "VEA", "VWO", "ITOT", "SPLG",
}

_SECTOR_ETF_PREFIXES = ("XL",)             # XLK, XLF, XLE, …
_SECTOR_ETF_SUFFIXES = ("_SECTOR_ETF",)    # placeholder for non-XL sector ETFs

_THEMATIC_KEYWORDS = (
    "ARK", "AI", "ROBO", "CYBR", "CLOU", "CLDF", "CIBR", "WCLD",
    "BOTZ", "BUG", "HACK", "SKYY", "FINX", "BLOK",
    "DRIV", "DRIVE", "ESPO", "GAMR", "VIDI",
    "ICLN", "TAN", "QCLN",
)


# ============================================================
# Result types
# ============================================================
@dataclass
class TopETF:
    asset:           str
    name:            str
    weight_pct:      Optional[float]
    shares:          Optional[float]
    market_value:    Optional[float]


@dataclass
class ETFHoldings:
    available: bool
    n_total_etfs: int = 0
    total_etf_shares: Optional[float] = None

    in_major_index: bool = False
    sector_etfs_count: int = 0
    thematic_etfs_count: int = 0
    broad_index_count: int = 0

    top_etfs: list[TopETF] = field(default_factory=list)
    largest_holder: Optional[TopETF] = None

    note: str = ""


# ============================================================
# Helpers
# ============================================================
def _classify_etf(symbol: str) -> str:
    sym = (symbol or "").upper()
    if sym in _BROAD_INDEX_ETFS:
        return "broad_index"
    for pre in _SECTOR_ETF_PREFIXES:
        if sym.startswith(pre):
            return "sector"
    for kw in _THEMATIC_KEYWORDS:
        if kw in sym:
            return "thematic"
    return "other"


def _to_top_etf(row: pd.Series) -> TopETF:
    return TopETF(
        asset=str(row.get("asset") or row.get("symbol") or ""),
        name=str(row.get("name") or row.get("etfName") or ""),
        weight_pct=float(row["weightPercentage"]) if pd.notna(row.get("weightPercentage")) else None,
        shares=float(row["sharesNumber"]) if pd.notna(row.get("sharesNumber")) else None,
        market_value=float(row["marketValue"]) if pd.notna(row.get("marketValue")) else None,
    )


# ============================================================
# Public API
# ============================================================
def analyze_etf_holdings(ticker: str) -> ETFHoldings:
    try:
        from data import fmp_extras
    except Exception:
        return ETFHoldings(available=False, note="fmp_extras unavailable")

    if not fmp_extras.is_available():
        return ETFHoldings(
            available=False,
            note="FMP_API_KEY not configured. ETF holdings is FMP-only.",
        )

    df = fmp_extras.fetch_etf_holders(ticker)
    if df.empty:
        return ETFHoldings(
            available=False,
            note="No ETF holders returned by FMP for this ticker.",
        )

    # Normalise the symbol column name (FMP has shipped both `asset`
    # and `symbol` in different versions of this endpoint)
    if "asset" not in df.columns and "symbol" in df.columns:
        df = df.rename(columns={"symbol": "asset"})
    if "asset" not in df.columns:
        return ETFHoldings(
            available=False,
            note="ETF response missing an 'asset' / 'symbol' column.",
        )

    df["category"] = df["asset"].apply(_classify_etf)

    broad_index_count = int((df["category"] == "broad_index").sum())
    sector_count = int((df["category"] == "sector").sum())
    thematic_count = int((df["category"] == "thematic").sum())
    in_major_index = broad_index_count > 0

    total_shares = (
        float(df["sharesNumber"].sum()) if "sharesNumber" in df.columns else None
    )

    # Top 10 by weight
    if "weightPercentage" in df.columns:
        top_df = df.nlargest(10, "weightPercentage")
    else:
        top_df = df.head(10)
    top = [_to_top_etf(r) for _, r in top_df.iterrows()]

    largest = top[0] if top else None

    return ETFHoldings(
        available=True,
        n_total_etfs=int(len(df)),
        total_etf_shares=total_shares,
        in_major_index=in_major_index,
        sector_etfs_count=sector_count,
        thematic_etfs_count=thematic_count,
        broad_index_count=broad_index_count,
        top_etfs=top,
        largest_holder=largest,
    )
