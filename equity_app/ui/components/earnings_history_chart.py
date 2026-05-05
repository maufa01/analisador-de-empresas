"""
Earnings track-record component — beat-rate header + Plotly bar chart
of EPS surprise per quarter (green for beats, red for misses).

Reads from ``analysis.earnings_track_record.EarningsHistory``.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.earnings_track_record import EarningsHistory
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


def _consistency_color(label: str) -> str:
    return {
        "high":   "var(--gains)",
        "medium": "var(--accent)",
        "low":    "var(--losses)",
    }.get(label.lower(), "var(--text-muted)")


def _build_surprise_chart(df: pd.DataFrame, height: int = 240) -> go.Figure:
    fig = go.Figure()
    if df is None or df.empty or "surprise_pct" not in df.columns:
        fig.update_layout(
            height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            margin=dict(l=0, r=0, t=10, b=0),
            annotations=[dict(text="No surprise data", showarrow=False,
                              font=dict(color=TEXT_MUTED, size=12),
                              x=0.5, y=0.5, xref="paper", yref="paper")],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    sorted_df = df.sort_index()                            # oldest left, newest right
    x_labels = [
        d.strftime("%Y-Q%q") if hasattr(d, "strftime") else str(d)
        for d in sorted_df.index
    ]
    # Q labels via quarter math when possible; otherwise just dates.
    x_labels = []
    for d in sorted_df.index:
        try:
            ts = pd.Timestamp(d)
            x_labels.append(f"{ts.year} Q{((ts.month - 1) // 3) + 1}")
        except Exception:
            x_labels.append(str(d))

    values = sorted_df["surprise_pct"].fillna(0).values
    colors = [GAINS if v >= 0 else LOSSES for v in values]

    fig.add_trace(go.Bar(
        x=x_labels, y=values,
        marker=dict(color=colors),
        hovertemplate="<b>%{x}</b><br>Surprise %{y:+.2f}%<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False,
                   type="category"),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=True, ticksuffix="%"),
        bargap=0.35,
    )
    return fig


def render_earnings_track_record(history: EarningsHistory) -> None:
    """Render header + chart + recent-quarters table."""
    df = history.quarters

    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'⚠ {history.note or "No earnings history available for this ticker."}'
            '<br><span style="font-size:11px;">'
            'yfinance only ships the last ~4 quarters; longer track records '
            'become available when the FMP provider is wired in.'
            '</span></div>',
            unsafe_allow_html=True,
        )
        return

    # Header metrics
    c1, c2, c3, c4 = st.columns(4)
    if history.beat_rate is not None:
        c1.metric("BEAT RATE", f"{history.beat_rate * 100:.0f}%",
                  help="Share of quarters beating the consensus EPS estimate.")
    else:
        c1.metric("BEAT RATE", "—")

    if history.avg_surprise is not None:
        c2.metric("AVG SURPRISE", f"{history.avg_surprise:+.2f}%")
    else:
        c2.metric("AVG SURPRISE", "—")

    cons_color = _consistency_color(history.consistency)
    c3.markdown(
        '<div data-testid="stMetric">'
        '<div style="color:var(--text-muted); font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase;">CONSISTENCY</div>'
        f'<div style="color:{cons_color}; font-size:24px; font-weight:500; '
        f'letter-spacing:-0.3px; margin-top:2px;">'
        f'{history.consistency.upper()}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if history.next_date:
        c4.metric("NEXT EARNINGS", history.next_date[:10])
    else:
        c4.metric("NEXT EARNINGS", "—")

    # Chart
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        _build_surprise_chart(df, height=240),
        use_container_width=True, config={"displayModeBar": False},
    )

    # Recent-quarters table
    cols_to_show = [c for c in
                     ("eps_estimate", "eps_actual", "surprise_pct")
                     if c in df.columns]
    if cols_to_show:
        table = df[cols_to_show].copy().sort_index(ascending=False)
        table = table.rename(columns={
            "eps_estimate":  "EPS Estimate",
            "eps_actual":    "EPS Actual",
            "surprise_pct":  "Surprise %",
        })
        st.dataframe(
            table, use_container_width=True,
            column_config={
                "EPS Estimate": st.column_config.NumberColumn(format="%.2f"),
                "EPS Actual":   st.column_config.NumberColumn(format="%.2f"),
                "Surprise %":   st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

    if history.note:
        st.caption(history.note)
    st.caption(
        "yfinance ships up to ~4 recent quarters of surprise data; "
        "extending to 16+ quarters lands when the FMP provider goes live."
    )
