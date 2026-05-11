"""
Compare — Quality Scorecard with heatmapped cells.

12 quality metrics rendered as a pandas Styler with per-row gradient.
For higher-better metrics the highest ticker is green, the lowest is
copper; lower-better is inverted. The composite row averages each
ticker's intra-row percentile across all metrics.

Metrics that resolve to NaN for ALL tickers are dropped so the
scorecard never shows a row of em-dashes.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from analysis.ratios import _get, cagr, calculate_ratios, free_cash_flow


# (label, higher_is_better)  — the value function is dispatched below
_METRICS = [
    ("Revenue 5y CAGR",   True),
    ("FCF 5y CAGR",       True),
    ("Gross margin avg",  True),
    ("Op margin avg",     True),
    ("Net margin avg",    True),
    ("FCF margin avg",    True),
    ("ROIC latest",       True),
    ("ROE latest",        True),
    ("Asset turnover",    True),
    ("Net Debt/EBITDA",   False),
    ("Interest coverage", True),
    ("Cash conversion",   True),
]


def _last_finite(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    s = series.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if np.isfinite(v) else None


def _mean_finite(series: Optional[pd.Series], n: int = 5) -> Optional[float]:
    if series is None:
        return None
    s = series.dropna().tail(n)
    if s.empty:
        return None
    v = float(s.mean())
    return v if np.isfinite(v) else None


def _compute_row(bundle, ratios: pd.DataFrame) -> dict[str, Optional[float]]:
    """Compute the 12 metrics for one ticker. Values are in NATIVE units
    (CAGR / margin = decimal fraction; ROIC/ROE already %; ratios are
    plain numbers). Display formatting happens in `_format_row`."""
    out: dict[str, Optional[float]] = {}

    rev = _get(bundle.income, "revenue")
    out["Revenue 5y CAGR"] = (cagr(rev, periods=5)
                              if rev is not None else None)
    if out["Revenue 5y CAGR"] is not None and not np.isfinite(out["Revenue 5y CAGR"]):
        out["Revenue 5y CAGR"] = None

    fcf = free_cash_flow(bundle.cash)
    if fcf is not None:
        # Take abs of starting value for CAGR; cagr() rejects non-positive
        # starts so a negative starting FCF will return None, which is OK
        cf = cagr(fcf, periods=5)
        out["FCF 5y CAGR"] = cf if np.isfinite(cf) else None
    else:
        out["FCF 5y CAGR"] = None

    # Margins (in %)
    out["Gross margin avg"] = _mean_finite(ratios.get("Gross Margin %"))
    out["Op margin avg"]    = _mean_finite(ratios.get("Operating Margin %"))
    out["Net margin avg"]   = _mean_finite(ratios.get("Net Margin %"))
    out["FCF margin avg"]   = _mean_finite(ratios.get("FCF Margin %"))

    # Latest returns (already in %)
    out["ROIC latest"] = _last_finite(ratios.get("ROIC %"))
    out["ROE latest"]  = _last_finite(ratios.get("ROE %"))

    # Asset turnover = revenue / total_assets (latest)
    ta = _get(bundle.balance, "total_assets")
    if rev is not None and ta is not None:
        try:
            common = rev.index.intersection(ta.index)
            if len(common):
                last_rev = float(rev.loc[common].dropna().iloc[-1])
                last_ta = float(ta.loc[common].dropna().iloc[-1])
                out["Asset turnover"] = (last_rev / last_ta) if last_ta > 0 else None
            else:
                out["Asset turnover"] = None
        except Exception:
            out["Asset turnover"] = None
    else:
        out["Asset turnover"] = None

    out["Net Debt/EBITDA"] = _last_finite(ratios.get("Net Debt/EBITDA"))
    out["Interest coverage"] = _last_finite(ratios.get("Interest Coverage"))
    out["Cash conversion"] = _last_finite(ratios.get("Cash Conversion"))

    return out


def _format_value(label: str, v: Optional[float]) -> str:
    if v is None or not isinstance(v, (int, float)) or not np.isfinite(v):
        return "—"
    if label in ("Revenue 5y CAGR", "FCF 5y CAGR"):
        return f"{v*100:+.1f}%"
    if label in ("Gross margin avg", "Op margin avg",
                  "Net margin avg", "FCF margin avg",
                  "ROIC latest", "ROE latest"):
        return f"{v:.1f}%"
    if label in ("Asset turnover", "Cash conversion"):
        return f"{v:.2f}"
    if label == "Net Debt/EBITDA":
        return f"{v:.2f}x"
    if label == "Interest coverage":
        return f"{v:.1f}x"
    return f"{v:.2f}"


def _row_percentile(values: list[Optional[float]], higher_better: bool) -> list[Optional[float]]:
    """Return a 0..1 percentile rank per cell (None if its value is None
    OR if every other value is None / equal — flat row gets 0.5 for all
    non-None cells)."""
    finite_vals = [v for v in values if v is not None and np.isfinite(v)]
    if not finite_vals:
        return [None] * len(values)
    vmin, vmax = min(finite_vals), max(finite_vals)
    if vmax == vmin:
        return [0.5 if v is not None else None for v in values]
    out: list[Optional[float]] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        norm = (v - vmin) / (vmax - vmin)
        out.append(norm if higher_better else 1.0 - norm)
    return out


def _grad_color(pct: Optional[float]) -> str:
    """Map 0..1 percentile to a copper→amber→green gradient."""
    if pct is None:
        return ""
    palette = ["#5B3A1F", "#7A5326", "#8B5C2C",
               "#A07A3A", "#7F9D5C", "#3F6F47", "#274234"]
    idx = max(0, min(int(pct * (len(palette) - 1)), len(palette) - 1))
    return f"background-color: {palette[idx]};"


def render_quality_scorecard(bundles: dict, market_caps: dict) -> None:
    """Render the 12-metric quality scorecard.

    Args:
      bundles:     ticker -> HydratedBundle (financials hydrated)
      market_caps: ticker -> market_cap (used only if a metric needs it
                   — currently unused but kept in the signature for
                   future extension)
    """
    if not bundles:
        st.info("Quality scorecard needs at least one ticker.")
        return

    tickers: list[str] = []
    ratios_by_ticker: dict[str, pd.DataFrame] = {}
    for t, b in bundles.items():
        if b is None or b.income.empty:
            continue
        try:
            r = calculate_ratios(b.income, b.balance, b.cash)
        except Exception:
            r = pd.DataFrame()
        tickers.append(t)
        ratios_by_ticker[t] = r

    if not tickers:
        st.info("Quality scorecard needs financial history for at least one ticker.")
        return

    # Compute every metric × every ticker
    raw: dict[str, dict[str, Optional[float]]] = {}
    for t in tickers:
        raw[t] = _compute_row(bundles[t], ratios_by_ticker[t])

    # Drop rows where every value is None
    visible_metrics: list[tuple[str, bool]] = []
    for label, higher in _METRICS:
        if any(raw[t].get(label) is not None for t in tickers):
            visible_metrics.append((label, higher))

    if not visible_metrics:
        st.info("All scorecard metrics returned no data.")
        return

    # Build display + percentile grids
    display: dict[str, list[str]] = {t: [] for t in tickers}
    percentile_grid: list[list[Optional[float]]] = []
    composite_pct: dict[str, list[float]] = {t: [] for t in tickers}

    index_labels: list[str] = []
    for label, higher in visible_metrics:
        index_labels.append(label)
        values = [raw[t].get(label) for t in tickers]
        pcts = _row_percentile(values, higher)
        percentile_grid.append(pcts)
        for t, v, p in zip(tickers, values, pcts):
            display[t].append(_format_value(label, v))
            if p is not None:
                composite_pct[t].append(p)

    # Composite row
    composite_row: list[Optional[float]] = []
    composite_display: list[str] = []
    for t in tickers:
        if composite_pct[t]:
            avg = float(np.mean(composite_pct[t]))
            composite_row.append(avg)
            composite_display.append(f"{avg*100:.0f}")
        else:
            composite_row.append(None)
            composite_display.append("—")
    percentile_grid.append(composite_row)
    index_labels.append("Composite score")
    for t, val in zip(tickers, composite_display):
        display[t].append(val)

    df = pd.DataFrame(display, index=index_labels)

    # Per-cell colours from the percentile grid
    color_grid = [[_grad_color(p) for p in row] for row in percentile_grid]
    color_df = pd.DataFrame(color_grid, index=index_labels, columns=tickers)

    def _style(_: pd.DataFrame) -> pd.DataFrame:
        return color_df

    styled = df.style.apply(_style, axis=None)
    st.dataframe(styled, use_container_width=True)
    st.caption(
        "Per-row heatmap: highest score in each metric is green, lowest "
        "copper. Net Debt/EBITDA is inverted (lower is better). "
        "Composite score is each ticker's average intra-row percentile."
    )
