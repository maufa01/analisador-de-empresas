"""
Cash Conversion Cycle dashboard — 3-card row (DSO / DIO / DPO) with
trend arrows + a Plotly chart layering the historical CCC line over a
DSO/DIO/DPO stacked bar.

Reads from ``analysis.working_capital.CCCResult``.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.working_capital import CCCResult
from core.formatters import safe_fmt
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


def _arrow(curr: Optional[float], prev: Optional[float], *, lower_better: bool) -> str:
    """Return an inline-coloured trend arrow span."""
    if curr is None or prev is None:
        return ""
    diff = curr - prev
    if abs(diff) < 0.01:
        return '<span style="color:var(--text-muted);">→</span>'
    is_better = (diff < 0) if lower_better else (diff > 0)
    color = "var(--gains)" if is_better else "var(--losses)"
    arrow = "↓" if diff < 0 else "↑"
    return f'<span style="color:{color};">{arrow}</span>'


def _component_card(label: str, value: Optional[float], trend_arrow: str) -> str:
    text = f"{value:.0f}d" if value is not None else "—"
    return (
        '<div class="eq-card" style="padding:14px 16px;">'
        f'<div class="eq-idx-label">{label.upper()}</div>'
        '<div style="display:flex; align-items:baseline; gap:8px; margin-top:6px;">'
        f'<span style="color:var(--text-primary); font-size:24px; font-weight:500; '
        f'letter-spacing:-0.5px; font-variant-numeric:tabular-nums;">{text}</span>'
        f'<span style="font-size:18px;">{trend_arrow}</span>'
        '</div></div>'
    )


def _build_ccc_figure(history: pd.DataFrame, height: int = 280) -> go.Figure:
    fig = go.Figure()
    if history is None or history.empty:
        fig.update_layout(
            height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            margin=dict(l=0, r=0, t=10, b=0),
            annotations=[dict(text="No CCC history available", showarrow=False,
                              font=dict(color=TEXT_MUTED, size=12),
                              x=0.5, y=0.5, xref="paper", yref="paper")],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    x_labels = [d.strftime("%Y") if hasattr(d, "strftime") else str(d)
                for d in history.index]

    # DSO + DIO stacked above zero, DPO below zero — visually shows the
    # net = CCC line balancing them.
    if "DSO" in history.columns:
        fig.add_trace(go.Bar(
            x=x_labels, y=history["DSO"].values, name="DSO",
            marker=dict(color="rgba(201,169,97,0.55)"),
            hovertemplate="<b>%{x}</b><br>DSO %{y:.0f}d<extra></extra>",
        ))
    if "DIO" in history.columns:
        fig.add_trace(go.Bar(
            x=x_labels, y=history["DIO"].values, name="DIO",
            marker=dict(color="rgba(201,169,97,0.30)"),
            hovertemplate="<b>%{x}</b><br>DIO %{y:.0f}d<extra></extra>",
        ))
    if "DPO" in history.columns:
        fig.add_trace(go.Bar(
            x=x_labels, y=(-history["DPO"]).values, name="DPO",
            marker=dict(color="rgba(156,163,175,0.65)"),
            hovertemplate="<b>%{x}</b><br>DPO %{y:.0f}d<extra></extra>",
        ))
    if "CCC" in history.columns:
        fig.add_trace(go.Scatter(
            x=x_labels, y=history["CCC"].values,
            mode="lines+markers", name="CCC",
            line=dict(color=GAINS, width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>CCC %{y:.0f}d<extra></extra>",
        ))

    fig.update_layout(
        barmode="relative",
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, zeroline=False,
                   type="category"),
        yaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=True, ticksuffix="d"),
    )
    return fig


def render_ccc_dashboard(result: CCCResult) -> None:
    """Component cards + history chart + interpretation.

    Renders an "n/a" notice (instead of the full dashboard) when CCC
    couldn't be computed — typical for utilities / software / financials
    where there's no inventory cycle to track. P12.A2 fix.
    """
    # Empty-state: utilities, banks, software-only have no CCC.
    if (result is None
            or result.current_ccc is None
            or result.avg_5y_ccc is None
            or result.history is None
            or result.history.empty):
        st.markdown(
            '<div class="eq-card" '
            'style="padding:14px 18px; color:var(--text-muted); '
            'font-size:12px;">'
            '<b>Cash Conversion Cycle is not applicable.</b><br>'
            'Typical for utilities / software / financials — there is '
            'no inventory cycle to measure.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ---- 3 component cards ----
    history = result.history
    prev_dso = history["DSO"].iloc[-2] if len(history) >= 2 else None
    prev_dio = history["DIO"].iloc[-2] if len(history) >= 2 else None
    prev_dpo = history["DPO"].iloc[-2] if len(history) >= 2 else None

    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown(
            _component_card(
                "Days Sales Outstanding", result.current_dso,
                _arrow(result.current_dso, prev_dso, lower_better=True),
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _component_card(
                "Days Inventory Outstanding", result.current_dio,
                _arrow(result.current_dio, prev_dio, lower_better=True),
            ),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _component_card(
                "Days Payables Outstanding", result.current_dpo,
                _arrow(result.current_dpo, prev_dpo, lower_better=False),
            ),
            unsafe_allow_html=True,
        )

    # ---- CCC big number + interpretation ----
    if result.current_ccc is not None:
        ccc_color = (
            "var(--gains)" if result.is_negative_ccc
            else "var(--accent)" if (
                result.industry_avg_ccc is None
                or result.current_ccc < result.industry_avg_ccc
            )
            else "var(--losses)"
        )
        ccc_text = f"{result.current_ccc:+.0f} days"
    else:
        ccc_color = "var(--text-muted)"
        ccc_text = "—"

    industry_html = (
        f'<span style="color:var(--text-muted); font-size:12px; '
        f'margin-left:14px;">Industry avg ~'
        f'<b style="color:var(--text-secondary);">'
        f'{safe_fmt(result.industry_avg_ccc, ".0f")}d</b></span>'
        if result.industry_avg_ccc is not None else ""
    )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-card" '
        f'style="padding:18px 22px; border-left:4px solid {ccc_color};">'
        '<div class="eq-idx-label">CASH CONVERSION CYCLE</div>'
        '<div style="display:flex; align-items:baseline; gap:14px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:32px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{ccc_color}; font-variant-numeric:tabular-nums;">{ccc_text}</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'5y avg <b style="color:var(--text-secondary);">'
        f'{safe_fmt(result.avg_5y_ccc, ".0f")}d</b></span>'
        f'{industry_html}'
        '</div>'
        f'<div style="margin-top:10px; color:var(--text-secondary); '
        f'font-size:13px; line-height:1.5;">{result.interpretation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- History chart ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        _build_ccc_figure(result.history, height=300),
        use_container_width=True, config={"displayModeBar": False},
    )
