"""
Peer-ranking table — categorised percentile bars.

Reads from ``analysis.peer_ranking.PeerRankingResult`` and renders one
section per category (Growth · Profitability · Solvency · Valuation),
each with a horizontal percentile bar per metric.

Closing summary at the bottom highlights category-level averages so
the user gets the verdict without scrolling every metric.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from analysis.peer_ranking import PeerRankingResult, MetricRanking


def _bar_color(percentile: Optional[float]) -> str:
    if percentile is None:
        return "var(--text-muted)"
    if percentile >= 75:
        return "rgba(16,185,129,0.85)"
    if percentile >= 50:
        return "rgba(201,169,97,0.85)"
    if percentile >= 25:
        return "rgba(217,119,6,0.85)"
    return "rgba(239,68,68,0.85)"


def _fmt_value(metric: MetricRanking) -> str:
    if metric.target_value is None:
        return "—"
    if metric.metric in {"pe", "ev_ebitda", "ps", "pb"}:
        return f"{metric.target_value:.2f}x"
    if metric.metric.startswith("debt_to"):
        return f"{metric.target_value:.2f}"
    # Most others are percentages
    return f"{metric.target_value:.2f}%"


def _row_html(metric: MetricRanking) -> str:
    pct = metric.percentile
    fill = pct if pct is not None else 0.0
    color = _bar_color(pct)
    pct_text = f"{pct:.0f}" if pct is not None else "—"

    return (
        '<div style="margin-bottom:10px;">'
        '<div style="display:flex; justify-content:space-between; '
        'align-items:baseline; margin-bottom:4px;">'
        f'<span style="color:var(--text-primary); font-size:13px; '
        f'font-weight:500;">{metric.label}</span>'
        '<span>'
        f'<span style="color:var(--text-secondary); font-size:12px; '
        f'font-variant-numeric:tabular-nums; margin-right:10px;">'
        f'{_fmt_value(metric)}</span>'
        f'<span style="color:var(--text-primary); font-size:13px; '
        f'font-variant-numeric:tabular-nums;">p={pct_text}</span>'
        '</span></div>'
        '<div style="background:var(--surface-raised); height:6px; '
        'border-radius:3px; overflow:hidden;">'
        f'<div style="background:{color}; width:{fill}%; height:100%;"></div>'
        '</div>'
        '<div style="display:flex; justify-content:space-between; '
        'margin-top:4px;">'
        f'<span style="color:var(--text-muted); font-size:11px;">'
        f'{metric.flag} {metric.band}</span>'
        f'<span style="color:var(--text-muted); font-size:11px;">'
        f'{metric.n_peers} peers</span>'
        '</div></div>'
    )


def _category_summary(category: str, avg_percentile: Optional[float]) -> str:
    if avg_percentile is None:
        verdict = "—"
        verdict_color = "var(--text-muted)"
    elif avg_percentile >= 75:
        verdict = "Top tier"
        verdict_color = "var(--gains)"
    elif avg_percentile >= 50:
        verdict = "Above median"
        verdict_color = "var(--accent)"
    elif avg_percentile >= 25:
        verdict = "Below median"
        verdict_color = "rgba(217,119,6,1)"
    else:
        verdict = "Bottom tier"
        verdict_color = "var(--losses)"

    avg_text = f"{avg_percentile:.0f}" if avg_percentile is not None else "—"
    return (
        '<div style="display:flex; justify-content:space-between; '
        'align-items:baseline; padding:8px 0; '
        'border-bottom:1px solid var(--border); font-size:13px;">'
        f'<span style="color:var(--text-primary); font-weight:500;">{category}</span>'
        '<span>'
        f'<span style="color:var(--text-muted); font-size:11px; '
        f'margin-right:8px;">avg p={avg_text}</span>'
        f'<span style="color:{verdict_color}; font-weight:500;">{verdict}</span>'
        '</span></div>'
    )


# ============================================================
# Public API
# ============================================================
def render_peer_ranking(result: PeerRankingResult) -> None:
    if not result.by_category:
        st.info("No peer-ranking data available — peer group is empty.")
        return

    st.markdown(
        f'<div class="eq-section-label">PEER RANKING · '
        f'{result.target_ticker} vs {result.n_peers} PEERS</div>',
        unsafe_allow_html=True,
    )

    # ---- Per-category sections ----
    for category, rankings in result.by_category.items():
        avg = result.avg_percentile.get(category)
        avg_text = f"{avg:.0f}" if avg is not None else "—"
        rows_html = "".join(_row_html(m) for m in rankings)
        st.markdown(
            '<div class="eq-card" style="padding:16px 18px; margin-top:10px;">'
            f'<div style="display:flex; justify-content:space-between; '
            f'align-items:baseline; margin-bottom:10px;">'
            f'<span class="eq-section-label" style="color:var(--accent);">'
            f'{category}</span>'
            f'<span style="color:var(--text-muted); font-size:11px;">'
            f'avg percentile {avg_text}</span></div>'
            + rows_html +
            '</div>',
            unsafe_allow_html=True,
        )

    # ---- Closing summary ----
    summary_html = "".join(
        _category_summary(cat, result.avg_percentile.get(cat))
        for cat in result.by_category
    )
    st.markdown(
        '<div class="eq-card" style="padding:16px 18px; margin-top:14px;">'
        '<div class="eq-section-label" style="margin-bottom:8px;">'
        'CATEGORY SUMMARY</div>'
        + summary_html +
        '</div>',
        unsafe_allow_html=True,
    )
