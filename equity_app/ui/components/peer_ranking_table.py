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
    """
    Strict palette — no bright oranges or coral reds. Mid-low percentiles
    get a darkened gold so the chart still reads as "premium dark" rather
    than a Material Design dashboard.
    """
    if percentile is None:
        return "var(--text-muted)"
    if percentile >= 75:
        return "rgba(16,185,129,0.85)"      # gains green — top quartile
    if percentile >= 50:
        return "rgba(201,169,97,0.85)"      # accent gold — above median
    if percentile >= 25:
        return "rgba(139,116,56,0.85)"      # darkened gold — below median
    return "rgba(184,115,51,0.85)"          # muted copper — bottom quartile


# Absolute "good-value" caps per metric: where a target-only bar would
# fill 100%. Without peer percentile we lean on sector-agnostic bands
# loosely calibrated to S&P 500 medians (e.g. ~10% net margin, ~15% ROE,
# P/E mid-20s in normal markets).
_HIGHER_BETTER_CAPS: dict[str, float] = {
    "operating_margin":  50.0,
    "net_margin":        30.0,
    "fcf_margin":        30.0,
    "roe":               30.0,
    "revenue_growth_1y": 30.0,
    "fcf_growth_5y":     30.0,
    "eps_growth_5y":     30.0,
    "earnings_yield":    10.0,
}
_LOWER_BETTER_CAPS: dict[str, float] = {
    "pe":              30.0,
    "ev_ebitda":       20.0,
    "ps":              10.0,
    "pb":               8.0,
    "debt_to_equity":   2.0,
}


def _target_only_bar(metric: MetricRanking) -> tuple[float, str]:
    """Return (fill_percent, color) for a target-only row.

    No peer baseline → map the raw target value through absolute
    market-norm thresholds. Net margin 30% (or higher) fills the bar;
    P/E 0 fills it, P/E ≥ 30 empties it. Color reuses the percentile
    palette so a 90%-filled bar still reads green.
    """
    v = metric.target_value
    if v is None:
        return 0.0, "var(--text-muted)"
    if metric.higher_better:
        cap = _HIGHER_BETTER_CAPS.get(metric.metric, 50.0)
        fill = (v / cap) * 100.0 if cap > 0 else 0.0
    else:
        cap = _LOWER_BETTER_CAPS.get(metric.metric, 30.0)
        # value at 0 ⇒ best; value ≥ cap ⇒ empty.
        fill = (1.0 - v / cap) * 100.0 if (v > 0 and cap > 0) else 100.0
    # Floor at 4% so the chip stays visible even for "off-the-chart"
    # values (P/E 50, P/B 60, etc.) — visually signals "way over cap"
    # instead of disappearing entirely.
    fill = max(4.0, min(100.0, fill))
    return fill, _bar_color(fill)


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
    has_pct = pct is not None
    has_target_value = metric.target_value is not None
    is_target_only = has_target_value and not has_pct and metric.n_peers == 0

    color = _bar_color(pct)

    # Right-side metric block: value + percentile (or italic note when target-only)
    if is_target_only:
        right_html = (
            f'<span style="color:var(--text-secondary); font-size:12px; '
            f'font-variant-numeric:tabular-nums;">{_fmt_value(metric)}</span>'
        )
    else:
        pct_text = f"{pct:.0f}" if has_pct else "—"
        right_html = (
            f'<span style="color:var(--text-secondary); font-size:12px; '
            f'font-variant-numeric:tabular-nums; margin-right:10px;">'
            f'{_fmt_value(metric)}</span>'
            f'<span style="color:var(--text-primary); font-size:13px; '
            f'font-variant-numeric:tabular-nums;">p={pct_text}</span>'
        )

    # Bar: target-only rows fill via absolute market-norm thresholds
    # (no peer baseline); other rows fill at their peer percentile.
    if is_target_only:
        to_fill, to_color = _target_only_bar(metric)
        bar_html = (
            '<div style="background:var(--surface-raised); height:6px; '
            'border-radius:3px; overflow:hidden;">'
            f'<div style="background:{to_color}; width:{to_fill}%; height:100%;"></div>'
            '</div>'
        )
    else:
        fill = pct if has_pct else 0.0
        bar_html = (
            '<div style="background:var(--surface-raised); height:6px; '
            'border-radius:3px; overflow:hidden;">'
            f'<div style="background:{color}; width:{fill}%; height:100%;"></div>'
            '</div>'
        )

    # Footer: explicit message for target-only rows; flag + band + peer
    # count for everything else.
    if is_target_only:
        reason = (metric.target_only_reason
                  or "Peer data unavailable for this metric.")
        footer_html = (
            '<div style="margin-top:4px;">'
            '<span style="color:var(--text-muted); font-size:11px; '
            'font-style:italic;">'
            f'Target-only — {reason}'
            '</span></div>'
        )
    elif metric.n_peers < 3:
        footer_html = (
            '<div style="display:flex; justify-content:space-between; '
            'margin-top:4px;">'
            f'<span style="color:var(--text-muted); font-size:11px;">'
            f'{metric.flag} {metric.band}</span>'
            f'<span style="color:var(--text-muted); font-size:11px; '
            f'font-style:italic;">'
            f'only {metric.n_peers} peer{"s" if metric.n_peers != 1 else ""} '
            f'with data</span>'
            '</div>'
        )
    else:
        footer_html = (
            '<div style="display:flex; justify-content:space-between; '
            'margin-top:4px;">'
            f'<span style="color:var(--text-muted); font-size:11px;">'
            f'{metric.flag} {metric.band}</span>'
            f'<span style="color:var(--text-muted); font-size:11px;">'
            f'{metric.n_peers} peers</span>'
            '</div>'
        )

    return (
        '<div style="margin-bottom:10px;">'
        '<div style="display:flex; justify-content:space-between; '
        'align-items:baseline; margin-bottom:4px;">'
        f'<span style="color:var(--text-primary); font-size:13px; '
        f'font-weight:500;">{metric.label}</span>'
        f'<span>{right_html}</span>'
        '</div>'
        + bar_html
        + footer_html
        + '</div>'
    )


def _summary_card_html(category: str, avg_percentile: Optional[float]) -> str:
    """One self-contained card per category — never truncated."""
    if avg_percentile is None:
        verdict = "Insufficient peer data"
        verdict_color = "var(--text-muted)"
        avg_text = "—"
    else:
        avg_text = f"p={avg_percentile:.0f}"
        if avg_percentile >= 75:
            verdict = "Top tier"
            verdict_color = "var(--gains)"
        elif avg_percentile >= 50:
            verdict = "Above median"
            verdict_color = "var(--accent)"
        elif avg_percentile >= 25:
            verdict = "Below median"
            verdict_color = "rgba(139,116,56,1)"          # darkened gold
        else:
            verdict = "Bottom tier"
            verdict_color = "rgba(184,115,51,1)"          # muted copper

    return (
        '<div class="eq-card" style="padding:14px 16px; min-height:110px;">'
        f'<div class="eq-section-label" style="color:var(--accent);">'
        f'{category.upper()}</div>'
        f'<div style="margin-top:6px; color:var(--text-primary); font-size:18px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'letter-spacing:-0.3px;">{avg_text}</div>'
        f'<div style="margin-top:6px; color:{verdict_color}; '
        f'font-size:13px; font-weight:500;">{verdict}</div>'
        '</div>'
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

    # ---- Closing summary — N cards, one per category, never truncated ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">CATEGORY SUMMARY</div>',
        unsafe_allow_html=True,
    )
    categories = list(result.by_category.keys())
    if categories:
        cols = st.columns(len(categories), gap="small")
        for col, cat in zip(cols, categories):
            with col:
                st.markdown(
                    _summary_card_html(cat, result.avg_percentile.get(cat)),
                    unsafe_allow_html=True,
                )

    # Inline interpretation hint for valuation metrics — answers the
    # "is p=50 in valuation good or bad?" question raised in feedback.
    st.caption(
        "Percentile is normalised to **100 = best**. For valuation and "
        "leverage metrics (P/E, P/B, Debt/Equity), a high percentile "
        "means the company is *cheaper* or *less levered* than peers, "
        "not the opposite."
    )
