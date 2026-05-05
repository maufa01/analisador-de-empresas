"""
Segments + geography panel — segment table with growth/share + Plotly
treemap, geography pie + table, optional SOTP per-share output.

Reads from ``analysis.segments``. All three results render the FMP
empty state when ``available=False``.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.segments import (
    SegmentsResult, GeographyResult, SOTPResult, SegmentMetric,
)
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS,
)


_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_billions(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12: return f"{sign}${av/1e12:,.2f}T"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.0f}M"
    return f"{sign}${av:,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.1f}%"


def _empty(title: str, note: str) -> None:
    st.markdown(
        '<div class="eq-card" style="padding:18px; '
        'color:var(--text-muted); font-size:13px;">'
        f'<span class="eq-section-label">{title}</span>'
        f'<div style="margin-top:8px;">{note}</div></div>',
        unsafe_allow_html=True,
    )


def _segment_table(metrics: list[SegmentMetric]) -> pd.DataFrame:
    rows = []
    for m in metrics:
        rows.append({
            "Segment":           m.name,
            "Revenue":           _fmt_billions(m.current_revenue),
            "Share":             f"{m.share_of_revenue_pct:.1f}%",
            "YoY":               _fmt_pct(m.yoy_change_pct),
            "5y CAGR":           _fmt_pct(m.cagr_5y_pct),
        })
    return pd.DataFrame(rows)


def _treemap(metrics: list[SegmentMetric], title: str) -> go.Figure:
    labels = [m.name for m in metrics]
    values = [m.current_revenue for m in metrics]
    text = [
        f"{m.share_of_revenue_pct:.1f}% · {_fmt_billions(m.current_revenue)}"
        for m in metrics
    ]
    fig = go.Figure(go.Treemap(
        labels=labels, values=values, parents=[""] * len(labels),
        text=text, textinfo="label+text",
        marker=dict(
            colors=[ACCENT] * len(labels),
            line=dict(color=BORDER, width=1),
        ),
        hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
    ))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=12),
    )
    return fig


# ============================================================
# Public renderers
# ============================================================
def render_segments_panel(res: SegmentsResult) -> None:
    if not res.available:
        _empty("REVENUE BY SEGMENT", res.note)
        return

    st.markdown(
        '<div class="eq-section-label">REVENUE BY SEGMENT · '
        f'{res.n_segments} SEGMENTS · TOTAL {_fmt_billions(res.total_revenue)}'
        '</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(_treemap(res.segments, "Segments"),
                    use_container_width=True,
                    config={"displayModeBar": False})
    st.dataframe(_segment_table(res.segments),
                 hide_index=True, use_container_width=True)


def render_geography_panel(res: GeographyResult) -> None:
    if not res.available:
        _empty("REVENUE BY GEOGRAPHY", res.note)
        return

    label_bits = [f"{res.n_regions} REGIONS",
                  f"TOTAL {_fmt_billions(res.total_revenue)}"]
    if res.domestic_pct is not None:
        label_bits.append(f"DOMESTIC {res.domestic_pct:.0f}%")
    st.markdown(
        '<div class="eq-section-label">REVENUE BY GEOGRAPHY · '
        + " · ".join(label_bits) + '</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(_treemap(res.regions, "Geography"),
                    use_container_width=True,
                    config={"displayModeBar": False})
    st.dataframe(_segment_table(res.regions),
                 hide_index=True, use_container_width=True)


def render_sotp_panel(res: SOTPResult) -> None:
    if not res.available:
        _empty("SOTP VALUATION", res.note or "Segments data required.")
        return

    color = GAINS
    if (res.premium_to_sotp_pct is not None
            and res.premium_to_sotp_pct > 0):
        color = _DOWNSIDE

    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">SOTP · IMPLIED VALUE FROM SEGMENT MULTIPLES</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        '<div>'
        '<div class="eq-idx-label">IMPLIED PER SHARE</div>'
        f'<div style="color:var(--text-primary); font-size:24px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">'
        f'${res.implied_per_share:,.2f}</div></div>'
        + (
            '<div>'
            '<div class="eq-idx-label">PREMIUM TO SOTP</div>'
            f'<div style="color:{color}; font-size:24px; '
            f'font-weight:500; font-variant-numeric:tabular-nums;">'
            f'{res.premium_to_sotp_pct:+.1f}%</div></div>'
            if res.premium_to_sotp_pct is not None else ""
        )
        + '<div>'
        '<div class="eq-idx-label">TOTAL EV</div>'
        f'<div style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">'
        f'{_fmt_billions(res.total_ev)}</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # Breakdown table
    rows = [{
        "Segment":      b.name,
        "Revenue":      _fmt_billions(b.revenue),
        "Multiple":     f"{b.multiple:.1f}×",
        "Method":       b.method,
        "Implied EV":   _fmt_billions(b.implied_ev),
        "Share of EV":  f"{b.share_of_value_pct:.1f}%",
    } for b in res.breakdown]
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)
    if res.note:
        st.caption(res.note)
