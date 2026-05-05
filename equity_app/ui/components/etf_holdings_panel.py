"""
ETF holdings panel — classification grid (broad index / sector /
thematic) + top-10 ETFs by weight + largest holder card.

Reads from ``analysis.etf_analysis.ETFHoldings``.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from analysis.etf_analysis import ETFHoldings


def _fmt_billions(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.0f}M"
    return f"{sign}${av:,.0f}"


def _fmt_shares(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e9: return f"{av/1e9:,.2f}B"
    if av >= 1e6: return f"{av/1e6:,.1f}M"
    if av >= 1e3: return f"{av/1e3:,.0f}K"
    return f"{av:,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%"


def render_etf_holdings_panel(res: ETFHoldings) -> None:
    if not res.available:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">ETF HOLDINGS</span>'
            f'<div style="margin-top:8px;">{res.note}</div></div>',
            unsafe_allow_html=True,
        )
        return

    # ---- Classification header ----
    badge = (
        '<span style="background:var(--gains); color:var(--bg-primary); '
        'padding:2px 10px; border-radius:4px; font-size:11px; '
        'font-weight:500; letter-spacing:0.4px;">IN MAJOR INDEX</span>'
        if res.in_major_index else
        '<span style="background:var(--surface-raised); '
        'color:var(--text-muted); '
        'padding:2px 10px; border-radius:4px; font-size:11px; '
        'font-weight:500; letter-spacing:0.4px;">NOT IN BROAD INDEX</span>'
    )
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px;">'
        f'<div class="eq-section-label">ETF HOLDINGS · {res.n_total_etfs} ETFs</div>'
        f'<div style="margin-top:8px;">{badge}</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Classification grid ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("BROAD INDEX", str(res.broad_index_count))
    c2.metric("SECTOR ETFs", str(res.sector_etfs_count))
    c3.metric("THEMATIC", str(res.thematic_etfs_count))
    c4.metric("TOTAL ETF SHARES", _fmt_shares(res.total_etf_shares))

    # ---- Largest holder card ----
    if res.largest_holder is not None:
        lh = res.largest_holder
        st.markdown(
            '<div class="eq-card" style="padding:14px 16px; margin-top:10px; '
            'border-left:3px solid var(--accent);">'
            '<div class="eq-idx-label">LARGEST ETF HOLDER</div>'
            f'<div style="color:var(--text-primary); font-size:18px; '
            f'font-weight:500; margin-top:6px;">{lh.asset}'
            + (f' <span style="color:var(--text-muted); font-size:12px; '
               f'font-weight:400; margin-left:8px;">{lh.name}</span>'
               if lh.name else "")
            + '</div>'
            '<div style="color:var(--accent); font-variant-numeric:tabular-nums; '
            f'margin-top:4px;">{_fmt_pct(lh.weight_pct)} weight · '
            f'{_fmt_billions(lh.market_value)} held</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ---- Top 10 table ----
    if res.top_etfs:
        rows = [{
            "ETF":           t.asset,
            "Name":          t.name or "—",
            "Weight":        _fmt_pct(t.weight_pct),
            "Shares held":   _fmt_shares(t.shares),
            "Market value":  _fmt_billions(t.market_value),
        } for t in res.top_etfs]
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'TOP 10 ETF HOLDERS BY WEIGHT</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)
