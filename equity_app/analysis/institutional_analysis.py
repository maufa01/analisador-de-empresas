"""
Institutional ownership snapshot — top holders + insider/institutional %.

Uses yfinance's ``Ticker`` accessors. yfinance only returns the top-10
slice as a snapshot — for 13F flow tracking and historical changes
wire FMP later.

Returns the empty result silently when yfinance can't resolve the
ticker; the UI renders a "data unavailable" placeholder.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import math
import re
import pandas as pd
import streamlit as st

from data.market_data import _yfinance


@dataclass
class HoldingsSnapshot:
    institutional: pd.DataFrame                       # top 10 institutionals
    mutual_funds:  pd.DataFrame                       # top 10 mutual funds
    insider_pct:        Optional[float] = None        # % of shares held by insiders
    institutional_pct:  Optional[float] = None        # % held by institutions
    note: str = ""


# ============================================================
# Internals
# ============================================================
def _coerce_holders(raw) -> pd.DataFrame:
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    # yfinance has shipped both "Holder" and "Organization" as the name
    # column over the years — normalise to "Holder".
    rename = {
        "Organization": "Holder",
        "% Out":        "pct_out",
        "% Held":       "pct_out",
        "% of Shares":  "pct_out",
        "Shares":       "shares",
        "Value":        "value_usd",
        "Date Reported": "date_reported",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "pct_out" in df.columns and df["pct_out"].dtype == object:
        # Strip % symbol if present
        df["pct_out"] = (
            df["pct_out"].astype(str).str.rstrip("%").astype(float, errors="ignore")
        )
    return df


def _parse_pct(value) -> Optional[float]:
    """Take a "12.34%" string or numeric and return a float in % units."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if not math.isfinite(v):
            return None
        # If the value looks like 0.05 (decimal), bump it to %; if it's
        # already 5.0 (already %), keep as is.
        return v * 100 if abs(v) < 1.5 else v
    s = str(value).strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_major_holders(raw) -> tuple[Optional[float], Optional[float]]:
    """
    yfinance's ``major_holders`` ships a tiny DataFrame with rows like
    ``("0.07%", "% of Shares Held by All Insider")``. Match by keyword.
    """
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return None, None

    insider_pct = None
    inst_pct = None
    for _, row in raw.iterrows():
        # Both columns can be either col 0 or col 1 depending on version
        cells = [str(c) for c in row.tolist()]
        joined = " ".join(cells).lower()
        for cell in cells:
            if re.match(r"^\s*[\d\.]+%?\s*$", str(cell)):
                num = _parse_pct(cell)
                if num is None:
                    continue
                if "insider" in joined:
                    insider_pct = num
                elif "institut" in joined:
                    inst_pct = num
                break
    return insider_pct, inst_pct


# ============================================================
# Public API
# ============================================================
@st.cache_data(ttl=21_600, show_spinner=False)
def get_holdings_snapshot(ticker: str) -> HoldingsSnapshot:
    yf = _yfinance()
    if yf is None or not ticker:
        return HoldingsSnapshot(
            institutional=pd.DataFrame(),
            mutual_funds=pd.DataFrame(),
            note="yfinance unavailable",
        )

    try:
        t = yf.Ticker(ticker)
    except Exception as e:
        return HoldingsSnapshot(
            institutional=pd.DataFrame(),
            mutual_funds=pd.DataFrame(),
            note=f"yfinance error: {e}",
        )

    inst_df = _coerce_holders(getattr(t, "institutional_holders", None))
    funds_df = _coerce_holders(getattr(t, "mutualfund_holders", None))
    insider_pct, inst_pct = _parse_major_holders(getattr(t, "major_holders", None))

    note = (
        ""
        if not (inst_df.empty and funds_df.empty)
        else "yfinance returned no holders data for this ticker"
    )

    return HoldingsSnapshot(
        institutional=inst_df,
        mutual_funds=funds_df,
        insider_pct=insider_pct,
        institutional_pct=inst_pct,
        note=note,
    )
