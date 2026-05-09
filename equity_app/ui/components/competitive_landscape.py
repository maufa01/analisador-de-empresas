"""
Competitive landscape — revenue-share donut + market-cap bar chart +
quick comparison table.

Without a live "market share" endpoint we use revenue-share within the
peer group as a proxy. The target ticker is highlighted in gold; peers
fall back to greys.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from valuation.comparables import PeerSnapshot
from analysis.ratios import _get
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GAINS, LOSSES,
)


_PEER_GREY_SHADES = ("#6E7480", "#8B919E", "#5C6370", "#9CA0A8", "#7A7F89")


def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _build_target_snapshot(
    ticker: str,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    market_cap: Optional[float],
) -> PeerSnapshot:
    last_inc = income.iloc[-1] if not income.empty else None
    last_bal = balance.iloc[-1] if not balance.empty else None

    def _pick(row, *keys):
        if row is None:
            return None
        for k in keys:
            if k in row and pd.notna(row[k]):
                return float(row[k])
        return None

    return PeerSnapshot(
        ticker=ticker,
        market_cap=market_cap,
        net_income=_pick(last_inc, "netIncome"),
        revenue=_pick(last_inc, "revenue"),
        ebitda=_pick(last_inc, "ebitda"),
        book_value=_pick(last_bal, "totalStockholdersEquity", "totalEquity"),
    )


def _revenue_yoy(income: pd.DataFrame) -> Optional[float]:
    rev = _get(income, "revenue")
    if rev is None or len(rev.dropna()) < 2:
        return None
    s = rev.dropna()
    if float(s.iloc[-2]) <= 0:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-2]) - 1.0) * 100.0


def _net_margin(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.revenue or p.revenue <= 0:
        return None
    return p.net_income / p.revenue * 100.0


def _roe(p: PeerSnapshot) -> Optional[float]:
    if p.net_income is None or not p.book_value or p.book_value <= 0:
        return None
    return p.net_income / p.book_value * 100.0


def _pe(p: PeerSnapshot) -> Optional[float]:
    if p.market_cap and p.net_income and p.net_income > 0:
        return p.market_cap / p.net_income
    return None


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e12: return f"${v / 1e12:,.2f}T"
    if av >= 1e9:  return f"${v / 1e9:,.2f}B"
    if av >= 1e6:  return f"${v / 1e6:,.1f}M"
    return f"${v:,.2f}"


# ============================================================
# Charts
# ============================================================
def _build_revenue_share_donut(
    target_label: str,
    revenues: dict[str, float],
    height: int = 280,
) -> go.Figure:
    labels = list(revenues.keys())
    values = list(revenues.values())
    target_idx = labels.index(target_label) if target_label in labels else -1
    colors = [
        ACCENT if i == target_idx
        else _PEER_GREY_SHADES[i % len(_PEER_GREY_SHADES)]
        for i in range(len(labels))
    ]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.6,
        marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
        textposition="outside",
        textinfo="label+percent",
        textfont=dict(family="Inter, sans-serif", size=11, color=TEXT_PRIMARY),
        sort=False,
        hovertemplate="<b>%{label}</b><br>Revenue $%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    if target_idx >= 0:
        target_pct = values[target_idx] / sum(values) * 100
        fig.update_layout(
            annotations=[dict(
                text=(f'<span style="font-size:18px; font-weight:500;">'
                      f'{target_pct:.1f}%</span><br>'
                      f'<span style="font-size:11px; color:#9CA3AF;">{target_label}</span>'),
                showarrow=False,
                font=dict(color=TEXT_PRIMARY, family="Inter, sans-serif"),
                x=0.5, y=0.5,
            )],
        )
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        showlegend=False,
    )
    return fig


def _build_market_cap_bar(
    target_label: str,
    market_caps: dict[str, float],
    height: int = 280,
) -> go.Figure:
    items = sorted(market_caps.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = [v / 1e9 for _, v in items]      # USD billions

    colors = [ACCENT if k == target_label else TEXT_MUTED for k in labels]

    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h",
        marker=dict(color=colors, line=dict(color=BORDER, width=0)),
        text=[f"${v:,.0f}B" if v < 1000 else f"${v / 1000:,.2f}T" for v in values],
        textposition="outside",
        textfont=dict(color=TEXT_PRIMARY, size=11),
        hovertemplate="<b>%{y}</b><br>Market cap $%{x:,.2f}B<extra></extra>",
    ))
    fig.update_layout(
        height=height, margin=dict(l=0, r=10, t=10, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, showgrid=True, gridcolor=BORDER,
                   zeroline=False, ticksuffix="B", tickprefix="$"),
        yaxis=dict(color=TEXT_PRIMARY, showgrid=False, zeroline=False,
                   autorange="reversed"),
        showlegend=False,
    )
    return fig


# ============================================================
# Public API
# ============================================================
def render_competitive_landscape(
    *,
    target_ticker: str,
    target_income: pd.DataFrame,
    target_balance: pd.DataFrame,
    target_market_cap: Optional[float],
    peers: list[PeerSnapshot],
) -> None:
    if not peers:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            'No peer data configured for this ticker.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    target = _build_target_snapshot(
        target_ticker, target_income, target_balance, target_market_cap,
    )
    all_subjects = [target] + peers

    # ---- Donut: revenue share ----
    revenues = {p.ticker: _safe(p.revenue) for p in all_subjects}
    revenues = {k: v for k, v in revenues.items() if v and v > 0}

    market_caps = {p.ticker: _safe(p.market_cap) for p in all_subjects}
    market_caps = {k: v for k, v in market_caps.items() if v and v > 0}

    col_l, col_r = st.columns(2, gap="medium")

    with col_l:
        st.markdown(
            '<div class="eq-section-label">REVENUE SHARE · PEER GROUP</div>',
            unsafe_allow_html=True,
        )
        if revenues and len(revenues) >= 2:
            st.plotly_chart(
                _build_revenue_share_donut(target_ticker, revenues),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info("Not enough revenue data across the peer group.")

    with col_r:
        st.markdown(
            '<div class="eq-section-label">MARKET CAP · PEER GROUP</div>',
            unsafe_allow_html=True,
        )
        if market_caps and len(market_caps) >= 2:
            st.plotly_chart(
                _build_market_cap_bar(target_ticker, market_caps),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info("Not enough market-cap data across the peer group.")

    # ---- Comparative table — tickers as rows, metrics as columns
    # so st.column_config handles per-metric formatting natively. ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">QUICK COMPARISON</div>',
        unsafe_allow_html=True,
    )

    rows: list[dict] = []
    for p in all_subjects:
        # Skip peers that came back empty (e.g. ticker not in FMP)
        if p.ticker != target_ticker and p.market_cap is None and p.revenue is None:
            continue
        rows.append({
            "Ticker":         p.ticker,
            "Market cap":     _safe(p.market_cap),
            "Revenue":        _safe(p.revenue),
            "Revenue YoY %":  (_revenue_yoy(target_income)
                               if p.ticker == target_ticker
                               else p.revenue_yoy),
            "Net margin %":   _net_margin(p),
            "P/E":            _pe(p),
            "ROE %":          _roe(p),
        })

    df = pd.DataFrame(rows).set_index("Ticker")

    # Industry-average row (mean across peers, excluding target).
    # Skip entirely when no peers survived hydration — otherwise the row
    # is just "None None None …" which reads like a UI bug.
    peer_only = df.drop(target_ticker, errors="ignore")
    if not peer_only.empty:
        industry_avg = peer_only.mean(numeric_only=True)
        industry_avg.name = "Industry avg"
        df = pd.concat([df, industry_avg.to_frame().T])

    # Style: highlight best per column (excluding the avg row)
    def _color_col(col: pd.Series) -> list[str]:
        lower_is_better = col.name == "P/E"
        # Drop the Industry avg row from the best/worst comparison
        peer_vals = col.drop("Industry avg", errors="ignore").dropna()
        if peer_vals.empty:
            return [""] * len(col)
        best  = peer_vals.min() if lower_is_better else peer_vals.max()
        worst = peer_vals.max() if lower_is_better else peer_vals.min()
        styles: list[str] = []
        for idx, val in col.items():
            if idx == "Industry avg" or pd.isna(val):
                styles.append("")
                continue
            if val == best and best != worst:
                styles.append("background-color: rgba(16,185,129,0.10);")
            elif val == worst and best != worst:
                styles.append("background-color: rgba(239,68,68,0.10);")
            else:
                styles.append("")
        return styles

    styled = (
        df.style
        .apply(_color_col, axis=0)
        .format({"Market cap": _fmt_money, "Revenue": _fmt_money}, na_rep="—")
        .set_properties(
            subset=pd.IndexSlice[[target_ticker], :],
            **{"font-weight": "500"},
        )
    )

    st.dataframe(
        styled,
        use_container_width=True,
        column_config={
            "Revenue YoY %": st.column_config.NumberColumn(format="%+.2f%%"),
            "Net margin %":  st.column_config.NumberColumn(format="%.2f%%"),
            "P/E":           st.column_config.NumberColumn(format="%.2fx"),
            "ROE %":         st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.caption(
        "Target ticker bold; best metric per column tinted green, "
        "worst tinted red. Industry avg = mean across peers."
    )
