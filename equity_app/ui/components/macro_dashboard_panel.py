"""
Macro overlay panel — regime header + yield curve chart + spread cards
+ vol/USD/credit metric grid.

Reads ``analysis.macro_dashboard.MacroSnapshot``.
"""
from __future__ import annotations
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

from analysis.macro_dashboard import MacroSnapshot
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS,
)


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
    "unknown": "var(--text-muted)",
}

_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%"


def _fmt_pp(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}pp"


def _fmt_2dp(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}"


def _yield_curve_figure(snap: MacroSnapshot) -> go.Figure:
    points = [
        ("3M",  snap.yield_3m),
        ("2Y*", snap.yield_2y),
        ("5Y",  snap.yield_5y),
        ("10Y", snap.yield_10y),
        ("30Y", snap.yield_30y),
    ]
    points = [(k, v) for k, v in points if v is not None]
    fig = go.Figure()
    if points:
        fig.add_trace(go.Scatter(
            x=[k for k, _ in points],
            y=[v for _, v in points],
            mode="lines+markers",
            line=dict(color=ACCENT, width=2),
            marker=dict(size=10, color=ACCENT),
            hovertemplate="<b>%{x}</b><br>%{y:.2f}%<extra></extra>",
        ))
    fig.update_layout(
        height=260, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, showgrid=False, type="category"),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, ticksuffix="%",
                   title="Yield"),
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY)),
    )
    return fig


def render_macro_panel(snap: MacroSnapshot) -> None:
    if not snap.available:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">MACRO DASHBOARD</span>'
            f'<div style="margin-top:8px;">{snap.note}</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(snap.regime.flag, "var(--text-muted)")

    # ---- Regime header ----
    reasons_html = " · ".join(snap.regime.reasons) if snap.regime.reasons else "—"
    st.markdown(
        '<div class="eq-card" style="padding:20px 24px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">MARKET REGIME</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:30px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color};">{snap.regime.label}</span>'
        f'<span style="color:var(--text-secondary); font-size:13px;">'
        f'{reasons_html}</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Yield curve chart ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'TREASURY YIELD CURVE</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(_yield_curve_figure(snap), use_container_width=True,
                    config={"displayModeBar": False})

    # ---- Spreads ----
    s1, s2 = st.columns(2, gap="small")

    def _spread_card(col, label: str, value: Optional[float], helper: str):
        if value is None:
            value_color = "var(--text-muted)"
            verdict = "—"
        elif value < 0:
            value_color = _DOWNSIDE
            verdict = "Inverted — recession signal"
        elif value < 0.5:
            value_color = "var(--accent)"
            verdict = "Flat — late-cycle"
        else:
            value_color = "var(--gains)"
            verdict = "Normal"
        with col:
            st.markdown(
                '<div class="eq-card" style="padding:14px 16px; '
                f'border-left:3px solid {value_color};">'
                f'<div class="eq-idx-label">{label}</div>'
                f'<div style="color:{value_color}; font-size:24px; '
                f'font-weight:500; font-variant-numeric:tabular-nums; '
                f'margin-top:6px;">{_fmt_pp(value)}</div>'
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:4px;">{helper}</div>'
                f'<div style="color:{value_color}; font-size:12px; '
                f'margin-top:4px;">{verdict}</div></div>',
                unsafe_allow_html=True,
            )

    _spread_card(s1, "2s10s SPREAD", snap.spread_2s10s,
                 "Classic recession indicator — 10Y minus 2Y")
    _spread_card(s2, "3M-10Y SPREAD", snap.spread_3m10y,
                 "Fed-favourite recession indicator")

    # ---- Vol / USD / Credit ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")

    if snap.vix is not None:
        vix_color = ("var(--gains)" if snap.vix < 15
                     else _DOWNSIDE if snap.vix > 25
                     else "var(--accent)")
        pct_str = (f"{snap.vix_percentile_1y:.0f}th pct (1y)"
                   if snap.vix_percentile_1y is not None else "")
        c1.metric("VIX", _fmt_2dp(snap.vix), pct_str)
    else:
        c1.metric("VIX", "—")

    c2.metric("DXY", _fmt_2dp(snap.dxy))

    if snap.hy_ig_proxy_z is not None:
        z_helper = "vs 1y mean — negative = wider HY spreads"
        c3.metric("HY/IG PROXY z", f"{snap.hy_ig_proxy_z:+.2f}σ", z_helper)
    else:
        c3.metric("HY/IG PROXY z", "—")

    c4.metric("REGIME SCORE", f"{snap.regime.score:+d}")

    if snap.note:
        st.caption(snap.note)
