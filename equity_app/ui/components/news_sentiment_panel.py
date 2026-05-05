"""
News sentiment panel — score header + pos/neutral/neg distribution +
top-10 headlines with per-item sentiment chip.

Reads from ``analysis.news_sentiment.NewsSentimentResult``.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from analysis.news_sentiment import NewsSentimentResult


_FLAG_COLOR = {
    "green":   "var(--gains)",
    "yellow":  "var(--accent)",
    "red":     "var(--losses)",
    "unknown": "var(--text-muted)",
}

_DOWNSIDE = "rgba(184,115,51,1)"


def _chip_color(value: float) -> str:
    if value > 0.10: return "var(--gains)"
    if value < -0.10: return _DOWNSIDE
    return "var(--text-muted)"


def _format_published(ts) -> str:
    if pd.isna(ts):
        return "—"
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def render_news_sentiment_panel(res: NewsSentimentResult) -> None:
    if not res.available:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">NEWS SENTIMENT</span>'
            f'<div style="margin-top:8px;">{res.note}</div></div>',
            unsafe_allow_html=True,
        )
        return

    color = _FLAG_COLOR.get(res.flag, "var(--text-muted)")

    # ---- Header ----
    score_str = f"{res.overall_score:+.2f}" if res.overall_score is not None else "—"
    change_str = (f"Δ7d {res.sentiment_change_7d:+.2f}"
                  if res.sentiment_change_7d is not None else "")
    spike_str = " · volume spike" if res.volume_spike else ""

    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color};">'
        '<div class="eq-section-label">NEWS SENTIMENT · '
        f'{res.engine.upper()}</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:28px; font-weight:500; '
        f'color:{color};">{res.overall_label}</span>'
        f'<span style="color:var(--text-primary); font-size:20px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">{score_str}</span>'
        + (f'<span style="color:var(--text-secondary); font-size:13px;">'
           f'{change_str}{spike_str}</span>' if change_str or spike_str else "")
        + '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Distribution ----
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("ITEMS", str(res.n_items))
    c2.metric("POSITIVE", str(res.positive_count))
    c3.metric("NEUTRAL", str(res.neutral_count))
    c4.metric("NEGATIVE", str(res.negative_count))

    # ---- Top headlines ----
    if res.items is None or res.items.empty:
        return

    items_html = ""
    for _, row in res.items.head(10).iterrows():
        sv = float(row.get("sentiment_value", 0))
        chip_color = _chip_color(sv)
        title = str(row.get("title", "")).replace("<", "&lt;")
        publisher = str(row.get("publisher", ""))
        link = str(row.get("link", "") or "#")
        published = _format_published(row.get("published"))

        items_html += (
            '<div style="padding:12px 0; border-bottom:1px solid var(--border); '
            'display:flex; gap:14px; justify-content:space-between;">'
            '<div style="flex:1; min-width:0;">'
            f'<a href="{link}" target="_blank" '
            'style="color:var(--text-primary); text-decoration:none; font-size:14px;">'
            f'{title}</a>'
            f'<div style="color:var(--text-muted); font-size:11px; margin-top:4px;">'
            f'{publisher} · {published}</div>'
            '</div>'
            f'<div style="color:{chip_color}; font-size:12px; '
            f'font-variant-numeric:tabular-nums; white-space:nowrap;">'
            f'{sv:+.2f}</div>'
            '</div>'
        )

    st.markdown(
        '<div class="eq-card" style="padding:6px 18px; margin-top:10px;">'
        '<div class="eq-section-label" style="margin-top:8px;">RECENT HEADLINES</div>'
        + items_html + '</div>',
        unsafe_allow_html=True,
    )
    if res.note:
        st.caption(res.note)
