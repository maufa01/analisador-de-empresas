"""
Composite-score breakdown — big rating verdict + 5 horizontal sub-score bars.

The verdict pill borrows colour from ``Rating.color`` (gold for HOLD,
emerald for BUY tiers, crimson for SELL tiers). Each sub-score bar is
0-100 with the explanation rendered as a small caption below.
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


def render_rating_pill(rating: Rating) -> None:
    """Big STRONG BUY / BUY / HOLD / SELL / STRONG SELL pill with reasoning."""
    confidence_label = rating.confidence.upper()
    confidence_color = {
        "HIGH":   "var(--gains)",
        "MEDIUM": "var(--accent)",
        "LOW":    "var(--losses)",
    }.get(confidence_label, "var(--text-muted)")

    upside_sign = "+" if rating.upside >= 0 else ""
    html = f"""
    <div class="eq-card" style="border-left: 4px solid {rating.color};
                                padding: 18px 22px;">
        <div class="eq-idx-label">RATING</div>
        <div style="display: flex; align-items: baseline; gap: 18px;
                    flex-wrap: wrap; margin-top: 4px;">
            <span style="font-size: 28px; font-weight: 500; letter-spacing: -0.5px;
                         color: {rating.color}; font-variant-numeric: tabular-nums;">
                {rating.verdict}
            </span>
            <span style="font-size: 13px; color: var(--text-secondary);">
                Composite <b style="color: var(--text-primary);">{rating.composite:.0f}</b>
                · Upside
                <b style="color: {'var(--gains)' if rating.upside >= 0 else 'var(--losses)'};">
                    {upside_sign}{rating.upside * 100:.1f}%
                </b>
                · Confidence
                <b style="color: {confidence_color};">{confidence_label}</b>
            </span>
        </div>
        <div style="margin-top: 8px; color: var(--text-muted);
                    font-size: 12px; line-height: 1.5;">{rating.reasoning}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_score_breakdown(score: ScoreBreakdown) -> None:
    """5 horizontal bars (Growth · Profitability · Solvency · EQ · Valuation)."""
    rows = [
        ("Growth",           score.growth,           score.explanations.get("growth")),
        ("Profitability",    score.profitability,    score.explanations.get("profitability")),
        ("Solvency",         score.solvency,         score.explanations.get("solvency")),
        ("Earnings quality", score.earnings_quality, score.explanations.get("earnings_quality")),
        ("Valuation",        score.valuation,        score.explanations.get("valuation")),
    ]

    bars_html = ""
    for label, value, expl in rows:
        if value is None:
            disp_value = "—"
            pct = 0
            color = "var(--text-muted)"
        else:
            disp_value = f"{value:.0f}"
            pct = max(0, min(100, int(value)))
            color = _bar_color(value)

        bars_html += f"""
        <div style="margin-bottom: 14px;">
            <div style="display: flex; justify-content: space-between;
                        align-items: baseline; margin-bottom: 4px;">
                <span class="eq-idx-label">{label}</span>
                <span style="font-variant-numeric: tabular-nums;
                             font-weight: 500; color: {color};
                             font-size: 14px;">{disp_value}</span>
            </div>
            <div style="background-color: var(--surface-raised); height: 6px;
                        border-radius: 3px; overflow: hidden;">
                <div style="background-color: {color}; width: {pct}%;
                            height: 100%; transition: width 0.3s ease;"></div>
            </div>
            <div style="color: var(--text-muted); font-size: 11px; margin-top: 4px;">
                {expl or ""}
            </div>
        </div>
        """

    st.markdown(
        f'<div class="eq-card" style="padding: 18px;">{bars_html}</div>',
        unsafe_allow_html=True,
    )
