"""
Wall Street consensus panel for the Valuation tab.

Two pieces:
    - Recommendation distribution bar (Strong Buy → Strong Sell)
    - Price-target card (mean / high / low / num analysts) with diff vs
      the app's aggregator intrinsic.

Source: Finnhub /stock/recommendation + /stock/price-target. Renders
nothing when no FINNHUB_API_KEY is configured.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"


def render_analyst_consensus_panel(
    ticker: str, *,
    aggregator_intrinsic: Optional[float] = None,
    current_price: Optional[float] = None,
) -> None:
    try:
        from data.finnhub_provider import (
            is_available, fetch_recommendation_trends, fetch_price_target,
        )
    except Exception:
        return
    if not is_available():
        return

    try:
        recs = fetch_recommendation_trends(ticker)
    except Exception:
        recs = pd.DataFrame()
    try:
        target = fetch_price_target(ticker) or {}
    except Exception:
        target = {}

    if (recs is None or recs.empty) and not target:
        return

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'WALL STREET CONSENSUS · FINNHUB</div>',
        unsafe_allow_html=True,
    )

    # ---- Distribution bar ----
    if recs is not None and not recs.empty:
        latest = recs.iloc[0]
        sb = int(latest.get("strongBuy", 0) or 0)
        b  = int(latest.get("buy", 0) or 0)
        h  = int(latest.get("hold", 0) or 0)
        s  = int(latest.get("sell", 0) or 0)
        ss = int(latest.get("strongSell", 0) or 0)
        total = sb + b + h + s + ss

        if total > 0:
            sb_pct = sb / total * 100
            b_pct  = b  / total * 100
            h_pct  = h  / total * 100
            s_pct  = s  / total * 100
            ss_pct = ss / total * 100

            # Pulled from theme palette — gains, accent gold, muted copper
            bar = (
                '<div style="display:flex; height:32px; border-radius:6px; '
                'overflow:hidden; background:var(--surface-raised);">'
                f'<div title="Strong Buy ({sb})" style="width:{sb_pct:.2f}%; '
                'background:rgba(16,185,129,0.95); display:flex; '
                'align-items:center; justify-content:center; color:#0B0E14; '
                'font-size:11px; font-weight:500;">'
                f'{sb if sb_pct > 8 else ""}</div>'
                f'<div title="Buy ({b})" style="width:{b_pct:.2f}%; '
                'background:rgba(16,185,129,0.55); display:flex; '
                'align-items:center; justify-content:center; color:#0B0E14; '
                'font-size:11px; font-weight:500;">'
                f'{b if b_pct > 8 else ""}</div>'
                f'<div title="Hold ({h})" style="width:{h_pct:.2f}%; '
                'background:rgba(201,169,97,0.85); display:flex; '
                'align-items:center; justify-content:center; color:#0B0E14; '
                'font-size:11px; font-weight:500;">'
                f'{h if h_pct > 8 else ""}</div>'
                f'<div title="Sell ({s})" style="width:{s_pct:.2f}%; '
                'background:rgba(184,115,51,0.85); display:flex; '
                'align-items:center; justify-content:center; color:#0B0E14; '
                'font-size:11px; font-weight:500;">'
                f'{s if s_pct > 8 else ""}</div>'
                f'<div title="Strong Sell ({ss})" style="width:{ss_pct:.2f}%; '
                'background:rgba(184,115,51,1); display:flex; '
                'align-items:center; justify-content:center; color:#FFFFFF; '
                'font-size:11px; font-weight:500;">'
                f'{ss if ss_pct > 8 else ""}</div>'
                '</div>'
            )

            period_str = ""
            if "period" in latest and pd.notna(latest["period"]):
                period_str = pd.Timestamp(latest["period"]).strftime("%b %Y")

            st.markdown(
                '<div class="eq-card" style="padding:18px 22px;">'
                '<div style="display:flex; justify-content:space-between; '
                'align-items:baseline; margin-bottom:10px;">'
                f'<span style="color:var(--text-muted); font-size:12px;">'
                f'{total} analysts · {period_str}</span>'
                '<span style="color:var(--text-muted); font-size:11px;">'
                'STRONG BUY · BUY · HOLD · SELL · STRONG SELL</span>'
                '</div>'
                + bar +
                '<div style="display:flex; justify-content:space-between; '
                'margin-top:8px; font-size:11px; color:var(--text-muted);">'
                f'<span>SB {sb}</span><span>B {b}</span>'
                f'<span>H {h}</span><span>S {s}</span><span>SS {ss}</span>'
                '</div></div>',
                unsafe_allow_html=True,
            )

    # ---- Price target ----
    if target:
        target_mean = target.get("targetMean")
        target_high = target.get("targetHigh")
        target_low  = target.get("targetLow")
        n_analysts = target.get("numberOfAnalysts")

        if isinstance(target_mean, (int, float)) and target_mean > 0:
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            cols = st.columns(4, gap="small")
            cols[0].metric("CONSENSUS TARGET", f"${target_mean:,.2f}",
                           f"{n_analysts} analysts" if n_analysts else "")
            cols[1].metric("HIGH",
                           f"${target_high:,.2f}" if isinstance(target_high, (int, float)) else "—")
            cols[2].metric("LOW",
                           f"${target_low:,.2f}" if isinstance(target_low, (int, float)) else "—")

            if isinstance(current_price, (int, float)) and current_price > 0:
                upside = (target_mean / current_price - 1) * 100
                cols[3].metric("UPSIDE vs PRICE", f"{upside:+.1f}%")
            else:
                cols[3].metric("UPSIDE vs PRICE", "—")

            # Divergence vs your model — only when both numbers exist and diff is material
            if (isinstance(aggregator_intrinsic, (int, float))
                    and aggregator_intrinsic > 0):
                diff_pct = (target_mean / aggregator_intrinsic - 1) * 100
                if abs(diff_pct) > 20:
                    color = "var(--accent)" if diff_pct < 0 else _DOWNSIDE
                    st.markdown(
                        '<div class="eq-card" style="padding:14px 16px; '
                        f'border-left:3px solid {color}; margin-top:10px;">'
                        '<div style="color:var(--text-primary); font-size:13px;">'
                        '<strong>Notable divergence with your model</strong></div>'
                        '<div style="color:var(--text-secondary); font-size:13px; '
                        'margin-top:4px;">'
                        f'Wall Street ${target_mean:,.2f} vs aggregator '
                        f'${aggregator_intrinsic:,.2f} '
                        f'<span style="color:{color}; '
                        f'font-variant-numeric:tabular-nums;">'
                        f'({diff_pct:+.1f}%)</span></div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
