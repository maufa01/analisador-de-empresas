"""
Insider activity panel — score header + summary metrics + cluster
events + executive activity (CEO + CFO) + recent transactions table.

Reads from ``analysis.insider_analysis.InsiderActivity``. Empty / no
key renders the FMP-required empty state.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.insider_analysis import InsiderActivity
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, GAINS,
)


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
    "unknown": "var(--text-muted)",
}
_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_usd(v: float) -> str:
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.1f}M"
    if av >= 1e3:  return f"{sign}${av/1e3:,.0f}K"
    return f"{sign}${av:,.0f}"


def _fmt_signed(v: float) -> str:
    av = abs(v)
    sign = "-" if v < 0 else "+"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.1f}M"
    if av >= 1e3:  return f"{sign}${av/1e3:,.0f}K"
    return f"{sign}${av:,.0f}"


def _empty(note: str) -> None:
    st.markdown(
        '<div class="eq-card" style="padding:18px; '
        'color:var(--text-muted); font-size:13px;">'
        '<span class="eq-section-label">INSIDER TRANSACTIONS</span>'
        f'<div style="margin-top:8px;">{note}</div></div>',
        unsafe_allow_html=True,
    )


def _activity_chart(df: pd.DataFrame) -> Optional[go.Figure]:
    if df.empty or "transactionDate" not in df.columns:
        return None
    df = df.dropna(subset=["transactionDate"]).copy()
    if df.empty:
        return None
    df["month"] = df["transactionDate"].dt.to_period("M").dt.to_timestamp()
    df["is_buy"] = df["transactionType"].astype(str).str.startswith("P")
    df["is_sell"] = df["transactionType"].astype(str).str.startswith("S")

    grouped = df.groupby("month").apply(
        lambda g: pd.Series({
            "buys":  g.loc[g["is_buy"], "transaction_value"].sum(),
            "sells": g.loc[g["is_sell"], "transaction_value"].sum(),
        })
    ).reset_index()

    fig = go.Figure()
    if not grouped.empty:
        fig.add_trace(go.Bar(
            x=grouped["month"], y=grouped["buys"] / 1e6,
            name="Buys", marker_color=GAINS,
            hovertemplate="<b>%{x|%b %Y}</b><br>Buys $%{y:.1f}M<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            x=grouped["month"], y=-grouped["sells"] / 1e6,
            name="Sells", marker_color=_DOWNSIDE,
            hovertemplate="<b>%{x|%b %Y}</b><br>Sells $%{y:.1f}M<extra></extra>",
        ))

    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        barmode="relative",
        xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, ticksuffix="M",
                   title="USD"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY)),
    )
    return fig


def render_insider_panel(res: InsiderActivity) -> None:
    if not res.available:
        _empty(res.note)
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    # ---- Header ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">INSIDER ACTIVITY · LAST 24 MONTHS</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:34px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{res.score}/100</span>'
        f'<span style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">'
        f'NET {_fmt_signed(res.net_activity_usd)}</span>'
        '</div>'
        '<div style="margin-top:8px; color:var(--text-secondary); '
        f'font-size:13px;">{res.interpretation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- Summary metrics ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("TRANSACTIONS", str(res.n_transactions))
    c2.metric("PURCHASES", str(res.n_purchases), _fmt_usd(res.total_bought_usd))
    c3.metric("SALES", str(res.n_sales), _fmt_usd(res.total_sold_usd))
    c4.metric("CLUSTERS", str(len(res.clusters)), "3+ insiders / 30 days")

    # ---- Trend ----
    trend_color = "var(--gains)" if res.trend == "increasing" else (
        _DOWNSIDE if res.trend == "decreasing" else "var(--text-muted)"
    )
    st.markdown(
        '<div class="eq-card" style="padding:14px 16px; margin-top:10px;">'
        '<div style="display:flex; gap:24px; flex-wrap:wrap;">'
        '<div>'
        '<div class="eq-idx-label">RECENT 6M NET</div>'
        f'<div style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{_fmt_signed(res.recent_6m_net_usd)}</div></div>'
        '<div>'
        '<div class="eq-idx-label">PRIOR 6M NET</div>'
        f'<div style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{_fmt_signed(res.prior_6m_net_usd)}</div></div>'
        '<div>'
        '<div class="eq-idx-label">TREND</div>'
        f'<div style="color:{trend_color}; font-size:18px; '
        f'font-weight:500; text-transform:uppercase; margin-top:4px;">'
        f'{res.trend}</div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Executive activity ----
    if res.ceo or res.cfo:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'EXECUTIVE ACTIVITY</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2, gap="small")
        for col, exec_, role in zip(cols, (res.ceo, res.cfo), ("CEO", "CFO")):
            with col:
                if exec_ is None:
                    st.markdown(
                        '<div class="eq-card" style="padding:14px 16px; '
                        'min-height:100px; color:var(--text-muted);">'
                        f'<div class="eq-idx-label">{role}</div>'
                        '<div style="margin-top:6px; font-size:13px;">'
                        'No transactions in window.</div></div>',
                        unsafe_allow_html=True,
                    )
                    continue
                exec_color = ("var(--gains)" if exec_.net_value_usd > 0
                              else _DOWNSIDE)
                st.markdown(
                    '<div class="eq-card" style="padding:14px 16px;">'
                    f'<div class="eq-idx-label">{exec_.role} ACTIVITY</div>'
                    f'<div style="color:{exec_color}; font-size:22px; '
                    f'font-weight:500; font-variant-numeric:tabular-nums; '
                    f'margin-top:6px;">{_fmt_signed(exec_.net_value_usd)}</div>'
                    '<div style="color:var(--text-muted); font-size:11px; '
                    f'margin-top:4px;">{exec_.n_buys} buys · {exec_.n_sells} sells '
                    f'· {exec_.n_transactions} transactions</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

    # ---- Cluster events ----
    if res.clusters:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'CLUSTER BUYING EVENTS</div>',
            unsafe_allow_html=True,
        )
        for c in res.clusters[:6]:
            names_str = ", ".join(c.insider_names[:5])
            if len(c.insider_names) > 5:
                names_str += " …"
            st.markdown(
                '<div class="eq-card" style="padding:12px 16px; '
                'border-left:3px solid var(--accent); margin-top:6px;">'
                '<div style="display:flex; justify-content:space-between; '
                'align-items:baseline; gap:12px;">'
                f'<div><strong style="color:var(--text-primary);">'
                f'{c.start_date.strftime("%b %Y")}</strong>'
                '<span style="color:var(--text-muted); margin-left:10px;">'
                f'{c.n_insiders} insiders</span></div>'
                f'<div style="color:var(--accent); font-weight:500; '
                f'font-variant-numeric:tabular-nums;">'
                f'{_fmt_usd(c.total_value_usd)}</div></div>'
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:6px;">{names_str}</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    # ---- Activity chart ----
    fig = _activity_chart(res.raw)
    if fig is not None:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'MONTHLY ACTIVITY</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    # ---- Recent transactions table ----
    df = res.raw.head(20).copy()
    if not df.empty:
        keep_cols = [c for c in ("transactionDate", "reportingName", "typeOfOwner",
                                  "transactionType", "securitiesTransacted",
                                  "price", "transaction_value") if c in df.columns]
        df = df[keep_cols]
        if "transactionDate" in df.columns:
            df["transactionDate"] = df["transactionDate"].dt.strftime("%Y-%m-%d")
        if "securitiesTransacted" in df.columns:
            df["securitiesTransacted"] = pd.to_numeric(
                df["securitiesTransacted"], errors="coerce"
            ).map(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce").map(
                lambda x: f"${x:.2f}" if pd.notna(x) else "—"
            )
        if "transaction_value" in df.columns:
            df["transaction_value"] = df["transaction_value"].map(_fmt_usd)
        rename = {
            "transactionDate":      "Date",
            "reportingName":        "Insider",
            "typeOfOwner":          "Role",
            "transactionType":      "Type",
            "securitiesTransacted": "Shares",
            "price":                "Price",
            "transaction_value":    "Value",
        }
        df = df.rename(columns=rename)
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'LAST 20 TRANSACTIONS</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(df, hide_index=True, use_container_width=True)
