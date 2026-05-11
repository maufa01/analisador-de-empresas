"""Portfolio stress tests — 5 hardcoded historical / hypothetical scenarios."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---- Scenario sector shock tables ----
# Each dict: ticker_sector → applied return (decimal). Sector strings
# match GICS. "_default" catches everything else.
_TECH_SELLOFF = {
    "Technology": -0.35,
    "Communication Services": -0.30,
    "Consumer Cyclical": -0.20,
    "Consumer Discretionary": -0.20,
    "_default": -0.10,
}
_RATE_SHOCK = {
    # +100bps rate move; equity sensitivities by sector duration proxy
    "Technology": -0.12,
    "Communication Services": -0.10,
    "Real Estate": -0.18,
    "Utilities": -0.15,
    "Consumer Staples": -0.05,
    "Healthcare": -0.06,
    "Industrials": -0.07,
    "Financial Services": 0.05,
    "Financials": 0.05,
    "Energy": 0.00,
    "Basic Materials": -0.05,
    "Materials": -0.05,
    "_default": -0.08,
}
_GFC_2008 = {
    "Financial Services": -0.55,
    "Financials": -0.55,
    "Real Estate": -0.50,
    "Energy": -0.50,
    "Technology": -0.45,
    "Communication Services": -0.40,
    "Consumer Cyclical": -0.50,
    "Consumer Discretionary": -0.50,
    "Industrials": -0.45,
    "Basic Materials": -0.45,
    "Materials": -0.45,
    "Utilities": -0.30,
    "Consumer Staples": -0.20,
    "Healthcare": -0.25,
    "_default": -0.40,
}
_COVID_2020 = {
    "Technology": 0.05,
    "Communication Services": -0.05,
    "Healthcare": 0.10,
    "Consumer Staples": -0.05,
    "Energy": -0.40,
    "Financial Services": -0.25,
    "Financials": -0.25,
    "Industrials": -0.30,
    "Real Estate": -0.30,
    "Utilities": -0.10,
    "Consumer Cyclical": -0.35,
    "Consumer Discretionary": -0.35,
    "Basic Materials": -0.20,
    "Materials": -0.20,
    "_default": -0.20,
}


def _apply(sector: Optional[str], table: dict) -> float:
    return float(table.get(sector or "_default", table.get("_default", 0.0)))


def render_stress_tests(
    holdings: dict[str, dict],
    current_prices: dict[str, float],
) -> None:
    """
    holdings: {ticker: {"weight": decimal, "sector": str|None, "value": float}}.
    current_prices: {ticker: latest price} — used to compute pre-shock value.
    """
    if not holdings:
        st.info("No holdings provided for stress testing.")
        return

    total_value = sum(float(h.get("value") or 0.0) for h in holdings.values())
    if total_value <= 0:
        st.info("Total portfolio value is zero — cannot stress test.")
        return

    scenarios = [
        ("Market −20% (broad selloff)", {"_default": -0.20}),
        ("Tech selloff (dot-com style)", _TECH_SELLOFF),
        ("Rate shock +100bps", _RATE_SHOCK),
        ("2008 replay (GFC sector drawdowns)", _GFC_2008),
        ("2020 COVID replay (mar 2020)", _COVID_2020),
    ]

    rows: list[dict] = []
    pl_pcts: list[float] = []
    for name, table in scenarios:
        # Apply per-holding shock based on sector
        per_holding: list[tuple[str, float, float]] = []  # (ticker, pct, $delta)
        new_value = 0.0
        for tkr, h in holdings.items():
            sector = h.get("sector")
            value = float(h.get("value") or 0.0)
            shock_pct = _apply(sector, table)
            holding_after = value * (1.0 + shock_pct)
            new_value += holding_after
            per_holding.append((tkr, shock_pct, holding_after - value))

        port_pl = new_value - total_value
        port_pl_pct = port_pl / total_value if total_value > 0 else 0.0
        per_holding.sort(key=lambda x: x[2])
        worst = per_holding[0] if per_holding else None
        best = per_holding[-1] if per_holding else None
        rows.append({
            "Scenario": name,
            "Portfolio P&L $": port_pl,
            "Portfolio P&L %": port_pl_pct * 100.0,
            "Worst": f"{worst[0]} ({worst[1]*100:+.0f}%)" if worst else "—",
            "Best": f"{best[0]} ({best[1]*100:+.0f}%)" if best else "—",
        })
        pl_pcts.append(port_pl_pct * 100.0)

    df = pd.DataFrame(rows)
    st.dataframe(
        df, hide_index=True, use_container_width=True,
        column_config={
            "Portfolio P&L $": st.column_config.NumberColumn(format="$%,.0f"),
            "Portfolio P&L %": st.column_config.NumberColumn(format="%+.1f%%"),
        },
    )

    # ---- Horizontal bar chart of scenario P&L % ----
    labels = [r["Scenario"] for r in rows]
    colors = [
        "rgba(46,196,182,0.85)" if v >= 0 else "rgba(230,57,70,0.85)"
        for v in pl_pcts
    ]
    fig = go.Figure(go.Bar(
        y=labels, x=pl_pcts, orientation="h",
        marker_color=colors,
        text=[f"{v:+.1f}%" for v in pl_pcts],
        textposition="outside",
        textfont=dict(size=11, color="rgba(255,255,255,0.85)"),
        hovertemplate="<b>%{y}</b><br>P&L %{x:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        height=max(220, 40 * len(labels) + 40),
        margin=dict(l=10, r=60, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=11,
                  color="rgba(255,255,255,0.85)"),
        xaxis=dict(ticksuffix="%", gridcolor="rgba(255,255,255,0.06)",
                   zeroline=True, zerolinecolor="rgba(255,255,255,0.3)",
                   tickfont=dict(size=10, color="rgba(255,255,255,0.55)")),
        yaxis=dict(autorange="reversed",
                   tickfont=dict(size=10, color="rgba(255,255,255,0.85)")),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    st.caption(
        "Stress scenarios use historical sector drawdowns as proxies. "
        "Estimates are directional, not precise — real crisis impact "
        "depends on the specific catalyst, position sizing within each "
        "sector, and individual idiosyncratic risk."
    )
