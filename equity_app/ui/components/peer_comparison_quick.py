"""
Quick peer comparison table for the Overview tab.

Compact table comparing the target ticker's headline metrics (P/E,
EV/EBITDA, P/S, ROE, Net Margin, Revenue growth) against the peer
group from ``valuation/comparables.PeerSnapshot``. Best value in each
row gets a subtle green tint; worst gets a subtle red tint.

Pure ``st.dataframe`` with ``Styler`` colouring — keeps the table fast
and copy-paste-able while still highlighting outliers.
"""
from __future__ import annotations
from typing import Optional

import math
import numpy as np
import pandas as pd
import streamlit as st

from valuation.comparables import PeerSnapshot, _peer_multiple
from analysis.ratios import _get


def _safe(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _net_margin(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.revenue or p.revenue <= 0:
        return None
    return p.net_income / p.revenue * 100.0


def _roe(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.book_value or p.book_value <= 0:
        return None
    return p.net_income / p.book_value * 100.0


# ============================================================
# Public API
# ============================================================
def render_peer_comparison_quick(
    *,
    target_ticker: str,
    target_income: pd.DataFrame,
    target_balance: pd.DataFrame,
    target_market_cap: Optional[float],
    target_enterprise_value: Optional[float],
    peers: list[PeerSnapshot],
) -> None:
    """
    Render the comparison table. Caller passes the target's financials
    + market cap so we can construct the same multiples on it.
    """
    if not peers:
        st.info("No peers configured for this ticker.")
        return

    # Build a synthetic PeerSnapshot for the target so we can reuse the
    # same multiple-extraction logic.
    last_inc = target_income.iloc[-1] if not target_income.empty else None
    last_bal = target_balance.iloc[-1] if not target_balance.empty else None

    def _pick(row, *keys):
        if row is None:
            return None
        for k in keys:
            if k in row and pd.notna(row[k]):
                return float(row[k])
        return None

    target = PeerSnapshot(
        ticker=target_ticker,
        market_cap=target_market_cap,
        enterprise_value=target_enterprise_value,
        net_income=_pick(last_inc, "netIncome"),
        revenue=_pick(last_inc, "revenue"),
        ebitda=_pick(last_inc, "ebitda"),
        book_value=_pick(last_bal, "totalStockholdersEquity", "totalEquity"),
    )

    # Revenue YoY growth — only available for the target (we have history)
    rev_series = _get(target_income, "revenue")
    target_rev_growth: Optional[float] = None
    if rev_series is not None and len(rev_series.dropna()) >= 2:
        s = rev_series.dropna()
        if float(s.iloc[-2]) > 0:
            target_rev_growth = (float(s.iloc[-1]) / float(s.iloc[-2]) - 1.0) * 100.0

    # ---- Build the wide DataFrame: rows = metrics, cols = tickers ----
    all_subjects = [target] + peers
    metric_rows: dict[str, dict[str, Optional[float]]] = {}

    metric_rows["P/E"] = {p.ticker: _safe(_peer_multiple(p, "pe")) for p in all_subjects}
    metric_rows["EV/EBITDA"] = {p.ticker: _safe(_peer_multiple(p, "ev_ebitda")) for p in all_subjects}
    metric_rows["P/S"] = {p.ticker: _safe(_peer_multiple(p, "ps")) for p in all_subjects}
    metric_rows["ROE %"] = {p.ticker: _roe(p) for p in all_subjects}
    metric_rows["Net Margin %"] = {p.ticker: _net_margin(p) for p in all_subjects}
    metric_rows["Revenue YoY %"] = {target_ticker: target_rev_growth}
    for p in peers:
        metric_rows["Revenue YoY %"][p.ticker] = None

    df = pd.DataFrame(metric_rows).T
    df.index.name = "Metric"

    # Sector mean column (excluding the target so the comparison is honest)
    df["Sector avg"] = df[[p.ticker for p in peers]].mean(axis=1, skipna=True)

    # ---- Style: subtle green for best, subtle red for worst per row ----
    def _row_color(row: pd.Series) -> list[str]:
        # "Better" direction depends on the metric
        lower_is_better = row.name in {"P/E", "EV/EBITDA", "P/S"}
        # Exclude the Sector avg column from best/worst so it stays neutral
        peer_cols = [c for c in row.index if c != "Sector avg"]
        peer_vals = row[peer_cols].dropna()
        if peer_vals.empty:
            return [""] * len(row)
        best_val = peer_vals.min() if lower_is_better else peer_vals.max()
        worst_val = peer_vals.max() if lower_is_better else peer_vals.min()

        styles: list[str] = []
        for col, val in row.items():
            if col == "Sector avg" or pd.isna(val):
                styles.append("")
                continue
            if val == best_val and best_val != worst_val:
                styles.append("background-color: rgba(16,185,129,0.10);")
            elif val == worst_val and best_val != worst_val:
                styles.append("background-color: rgba(239,68,68,0.10);")
            else:
                styles.append("")
        return styles

    styled = df.style.format(precision=2, na_rep="—").apply(_row_color, axis=1)

    # Bold the target column
    styled = styled.set_properties(
        subset=[target_ticker],
        **{"font-weight": "500"},
    )

    st.dataframe(styled, use_container_width=True)
