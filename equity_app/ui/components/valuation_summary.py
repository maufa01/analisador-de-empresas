"""
Valuation summary table — one row per model with implied per-share value
and upside vs the current price. Used in the Overview tab.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from core.valuation_pipeline import ValuationResults


def _row(model: str, value: Optional[float], current: Optional[float],
         note: str = "") -> dict:
    if value is None or not (current and current > 0):
        return {
            "Model":         model,
            "Intrinsic":     None,
            "Upside":        None,
            "Status":        note or "—",
        }
    return {
        "Model":         model,
        "Intrinsic":     float(value),
        # Upside in percent units so column_config formatter renders cleanly
        "Upside":        (value - current) / current * 100.0,
        "Status":        "OK",
    }


def render_valuation_summary(results: ValuationResults) -> None:
    """One row per model + an aggregator summary row at the bottom."""
    cur = results.current_price
    rows: list[dict] = [
        _row("DCF · 3-stage",
             results.dcf.intrinsic_value_per_share if results.dcf else None,
             cur, results.dcf_error or "—"),
        _row("Comparables (median)",
             (results.comparables.implied_per_share_median
              if results.comparables else None),
             cur, results.comparables_error or "—"),
        _row("Monte Carlo (median)",
             results.monte_carlo.median if results.monte_carlo else None,
             cur, results.monte_carlo_error or "—"),
        _row("Residual Income",
             (results.residual_income.intrinsic_value_per_share
              if results.residual_income else None),
             cur, results.ri_error or "—"),
        _row("DDM · 2-stage",
             results.ddm.intrinsic_value_per_share if results.ddm else None,
             cur, results.ddm_error or "—"),
        _row(f"AGGREGATOR · {results.aggregator.profile.upper()}",
             (results.aggregator.intrinsic_per_share
              if results.aggregator
              and pd.notna(results.aggregator.intrinsic_per_share) else None),
             cur,
             (f"{results.aggregator.n_models_used} models · "
              f"{results.aggregator.confidence}"
              if results.aggregator else "—")),
    ]
    df = pd.DataFrame(rows)
    df["Upside"] = df["Upside"].astype(float)
    st.dataframe(
        df, hide_index=True, use_container_width=True,
        column_config={
            "Intrinsic": st.column_config.NumberColumn(format="$%.2f"),
            "Upside":    st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )
