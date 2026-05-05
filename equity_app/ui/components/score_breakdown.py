"""
Composite-score breakdown — big rating verdict + 5 horizontal sub-score bars.

CRITICAL: every ``st.markdown(html, unsafe_allow_html=True)`` HTML string
in this file is a **single-line, no-leading-whitespace** string. Streamlit's
markdown parser runs BEFORE HTML rendering — any line with ≥4 leading
spaces is treated as a code block and the HTML leaks to the page as
literal text. The previous multi-line indented f-string version of this
file broke on Streamlit Cloud for that exact reason.

Building the whole component in one ``st.markdown`` call (rather than
opener / body / closer across multiple calls) is also intentional —
each ``st.markdown`` wraps its content in a fresh ``stMarkdownContainer``
div, so split calls would not produce a single ``.eq-card`` wrapper.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from scoring.scorer import ScoreBreakdown
from scoring.rating import Rating


def _bar_color(score: Optional[float]) -> str:
    if score is None:
        return "var(--text-muted)"
    if score >= 70:
        return "var(--gains)"
    if score <= 35:
        return "var(--losses)"
    return "var(--accent)"


# ============================================================
# Rating pill — single-line HTML only
# ============================================================
def render_rating_pill(rating: Rating) -> None:
    confidence_label = rating.confidence.upper()
    confidence_color = {
        "HIGH":   "var(--gains)",
        "MEDIUM": "var(--accent)",
        "LOW":    "var(--losses)",
    }.get(confidence_label, "var(--text-muted)")
    upside_color = "var(--gains)" if rating.upside >= 0 else "var(--losses)"
    upside_sign = "+" if rating.upside >= 0 else ""

    parts = [
        f'<div class="eq-card" style="border-left:4px solid {rating.color}; padding:18px 22px;">',
        '<div class="eq-idx-label">RATING</div>',
        '<div style="display:flex; align-items:baseline; gap:18px; flex-wrap:wrap; margin-top:4px;">',
        f'<span style="font-size:28px; font-weight:500; letter-spacing:-0.5px; color:{rating.color}; font-variant-numeric:tabular-nums;">{rating.verdict}</span>',
        '<span style="font-size:13px; color:var(--text-secondary);">',
        f'Composite <b style="color:var(--text-primary);">{rating.composite:.0f}</b> ',
        f'· Upside <b style="color:{upside_color};">{upside_sign}{rating.upside * 100:.1f}%</b> ',
        f'· Confidence <b style="color:{confidence_color};">{confidence_label}</b>',
        '</span>',
        '</div>',
        f'<div style="margin-top:8px; color:var(--text-muted); font-size:12px; line-height:1.5;">{rating.reasoning}</div>',
        '</div>',
    ]
    # Emit as ONE markdown call, joined without newlines so the parser
    # never sees indented lines.
    st.markdown("".join(parts), unsafe_allow_html=True)


# ============================================================
# Score breakdown — one st.markdown call with all 5 bars concatenated
# ============================================================
def _bar_html(label: str, value: Optional[float], explanation: Optional[str]) -> str:
    if value is None:
        disp_value = "—"
        pct = 0
        color = "var(--text-muted)"
    else:
        disp_value = f"{value:.0f}"
        pct = max(0, min(100, int(value)))
        color = _bar_color(value)

    expl_html = (
        f'<div style="color:var(--text-muted); font-size:11px; margin-top:4px;">{explanation}</div>'
        if explanation else ""
    )
    return (
        '<div style="margin-bottom:14px;">'
        '<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">'
        f'<span class="eq-idx-label">{label}</span>'
        f'<span style="font-variant-numeric:tabular-nums; font-weight:500; color:{color}; font-size:14px;">{disp_value}</span>'
        '</div>'
        '<div style="background-color:var(--surface-raised); height:6px; border-radius:3px; overflow:hidden;">'
        f'<div style="background-color:{color}; width:{pct}%; height:100%; transition:width 0.3s ease;"></div>'
        '</div>'
        f'{expl_html}'
        '</div>'
    )


def render_score_breakdown(score: ScoreBreakdown) -> None:
    """
    Original 5-bar layout — kept for backwards compat. New code should
    prefer ``render_score_breakdown_grid`` (Bloomberg-style 5-card row).
    """
    rows = [
        ("Growth",           score.growth,           score.explanations.get("growth")),
        ("Profitability",    score.profitability,    score.explanations.get("profitability")),
        ("Solvency",         score.solvency,         score.explanations.get("solvency")),
        ("Earnings quality", score.earnings_quality, score.explanations.get("earnings_quality")),
        ("Valuation",        score.valuation,        score.explanations.get("valuation")),
    ]

    body = "".join(_bar_html(label, value, expl) for label, value, expl in rows)
    st.markdown(
        f'<div class="eq-card" style="padding:18px;">{body}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Bloomberg-style 5-card grid (default for the Overview tab)
# ============================================================
def _grid_color(score_value: Optional[float]) -> str:
    """Score → color band per the spec (red / orange / gold / green)."""
    if score_value is None:
        return "var(--text-muted)"
    if score_value >= 75: return "var(--gains)"
    if score_value >= 50: return "var(--accent)"
    if score_value >= 25: return "#D97706"           # warm amber for the 25-50 band
    return "var(--losses)"


def _card_html(label: str, value: Optional[float], explanation: Optional[str]) -> str:
    if value is None:
        disp = "—"
        pct = 0
        color = "var(--text-muted)"
    else:
        disp = f"{value:.0f}"
        pct = max(0, min(100, int(value)))
        color = _grid_color(value)

    expl_html = (
        f'<div style="color:var(--text-muted); font-size:11px; margin-top:8px; '
        f'line-height:1.4; min-height:30px;">{explanation}</div>'
        if explanation else
        '<div style="margin-top:8px; min-height:30px;"></div>'
    )

    return (
        '<div style="background:var(--surface); border:1px solid var(--border); '
        'border-radius:8px; padding:14px 16px; min-height:140px;">'
        f'<div style="font-size:32px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums; line-height:1.1;">{disp}</div>'
        f'<div class="eq-idx-label" style="margin-top:4px;">{label.upper()}</div>'
        f'<div style="background:var(--surface-raised); height:2px; '
        f'border-radius:1px; margin-top:10px; overflow:hidden;">'
        f'<div style="background:{color}; width:{pct}%; height:100%;"></div>'
        f'</div>'
        f'{expl_html}'
        '</div>'
    )


def render_score_breakdown_grid(score: ScoreBreakdown) -> None:
    """
    5-card grid: each component as a separate card with the score in big
    tabular numerals, a 2px coloured bar, and the driver caption below.

    Each st.column gets one independent st.markdown (one-line HTML), so the
    indented-code-block trap doesn't apply.
    """
    items = [
        ("Growth",           score.growth,           score.explanations.get("growth")),
        ("Profitability",    score.profitability,    score.explanations.get("profitability")),
        ("Solvency",         score.solvency,         score.explanations.get("solvency")),
        ("Earnings quality", score.earnings_quality, score.explanations.get("earnings_quality")),
        ("Valuation",        score.valuation,        score.explanations.get("valuation")),
    ]
    cols = st.columns(len(items))
    for col, (label, value, explanation) in zip(cols, items):
        with col:
            st.markdown(
                _card_html(label, value, explanation),
                unsafe_allow_html=True,
            )
