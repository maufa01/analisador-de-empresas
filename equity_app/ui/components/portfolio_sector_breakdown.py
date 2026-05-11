"""Portfolio sector breakdown — donut + table + concentration warning."""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_sector_breakdown(holdings: dict[str, dict]) -> None:
    """
    holdings shape: {ticker: {"weight": float (decimal or pct), "sector": str|None}}.
    Unknown sectors bucket as "Unknown".
    """
    if not holdings:
        st.info("No holdings provided for sector breakdown.")
        return

    # Normalise weights to decimals summing to 1
    total = sum((h.get("weight") or 0.0) for h in holdings.values())
    if total <= 0:
        st.info("Weights must sum to a positive value.")
        return

    # Aggregate by sector
    by_sector: dict[str, dict] = {}
    for tkr, h in holdings.items():
        sector = h.get("sector") or "Unknown"
        bucket = by_sector.setdefault(sector, {"weight": 0.0, "count": 0})
        bucket["weight"] += (h.get("weight") or 0.0) / total
        bucket["count"] += 1

    sectors = sorted(by_sector.items(), key=lambda kv: kv[1]["weight"], reverse=True)
    sector_hhi = sum(b["weight"] ** 2 for _, b in sectors)
    top_sector = sectors[0]

    # Diagnostic banner
    if sector_hhi > 0.40:
        st.warning(
            f"Sector concentrated: **{top_sector[1]['weight']*100:.1f}%** "
            f"in {top_sector[0]} ({top_sector[1]['count']} position"
            f"{'s' if top_sector[1]['count'] != 1 else ''})."
        )

    # ---- Donut chart ----
    palette = [
        "#C9A14A", "#2EC4B6", "#6E7B8B", "#E63946",
        "#3B82F6", "#A78BFA", "#10B981", "#F59E0B",
        "#EC4899", "#14B8A6", "#8B5CF6", "#F97316",
    ]
    labels = [s[0] for s in sectors]
    values = [s[1]["weight"] * 100.0 for s in sectors]
    colors = [palette[i % len(palette)] for i in range(len(labels))]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0)", width=0)),
        textinfo="label+percent",
        textfont=dict(size=11, color="rgba(255,255,255,0.85)"),
        hovertemplate="<b>%{label}</b><br>Weight %{value:.1f}%<extra></extra>",
        sort=False,
    ))
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        annotations=[dict(
            text=f"<b>{len(holdings)}</b><br>holdings",
            showarrow=False, x=0.5, y=0.5,
            font=dict(size=14, color="rgba(255,255,255,0.85)"),
        )],
    )
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    # ---- Table ----
    with right:
        rows = []
        for sector, bucket in sectors:
            rows.append({
                "Sector": sector,
                "Weight %": bucket["weight"] * 100.0,
                "Holdings": bucket["count"],
            })
        # Append a "HHI" footer-style note via separate metric
        df = pd.DataFrame(rows)
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
                "Holdings": st.column_config.NumberColumn(format="%d"),
            },
        )
        chip_color = (
            "var(--gains)" if sector_hhi < 0.25
            else "var(--accent)" if sector_hhi < 0.40
            else "rgba(184,115,51,1)"
        )
        st.markdown(
            f'<div style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.6px; text-transform:uppercase;">SECTOR HHI</div>'
            f'<div style="color:{chip_color}; font-size:18px; font-weight:500; '
            f'margin-top:2px;">{sector_hhi:.3f}</div>',
            unsafe_allow_html=True,
        )
