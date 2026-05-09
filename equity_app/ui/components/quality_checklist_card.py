"""
Phil-Town / Pat-Dorsey style yes-no quality checklist UI.

Renders :class:`ChecklistResult` as a header score + per-category
tables with SI / NO / N/A pills next to each check.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from analysis.quality_checklist import run_checklist
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"
_NEUTRAL = TEXT_MUTED


_CATEGORY_LABELS = {
    "growth":             "Growth",
    "profitability":      "Profitability",
    "capital_allocation": "Capital allocation",
    "general":            "General",
}


def render_quality_checklist(income: pd.DataFrame,
                             balance: pd.DataFrame,
                             cash: pd.DataFrame) -> None:
    """SI / NO quality checklist with header score + per-category tables."""
    if income is None or income.empty:
        st.info("Quality checklist needs an income statement.")
        return

    result = run_checklist(income, balance, cash)

    # Header
    if result.score >= 70:
        score_color = GAINS
    elif result.score >= 40:
        score_color = ACCENT
    else:
        score_color = _DOWNSIDE

    st.markdown(
        f'<div style="background:{SURFACE}; padding:18px 20px; border-radius:8px;'
        f' border-left:3px solid {score_color}; margin-bottom:16px;">'
        '<div style="display:flex; justify-content:space-between; align-items:baseline;">'
        '<div>'
        f'<div style="color:{TEXT_MUTED}; font-size:11px; text-transform:uppercase; '
        f'letter-spacing:0.6px;">Quality checklist</div>'
        f'<div style="color:{TEXT_PRIMARY}; font-size:22px; font-weight:500; '
        f'margin-top:4px; font-variant-numeric:tabular-nums;">'
        f'{result.passed} / {result.applicable} checks passed'
        f'</div>'
        f'<div style="color:{TEXT_MUTED}; font-size:11px; margin-top:4px;">'
        f'{result.failed} failed · '
        f'{len(result.checks) - result.applicable} not calculable'
        f'</div>'
        '</div>'
        '<div style="text-align:right;">'
        f'<div style="color:{score_color}; font-size:36px; font-weight:600; '
        f'font-variant-numeric:tabular-nums;">{result.score:.0f}</div>'
        f'<div style="color:{TEXT_SECONDARY}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:0.6px;">Score</div>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Group by category
    by_cat: dict[str, list] = {}
    for c in result.checks:
        by_cat.setdefault(c.category, []).append(c)

    for cat, checks in by_cat.items():
        st.markdown(
            f'<div class="eq-section-label" style="margin-top:14px;">'
            f'{_CATEGORY_LABELS.get(cat, cat.title())}</div>',
            unsafe_allow_html=True,
        )

        rows_html: list[str] = []
        for c in checks:
            if c.result is True:
                icon, color, bg, label = "✓", GAINS, f"{GAINS}20", "SI"
            elif c.result is False:
                icon, color, bg, label = "✗", _DOWNSIDE, f"{_DOWNSIDE}20", "NO"
            else:
                icon, color, bg, label = "—", _NEUTRAL, f"{_NEUTRAL}20", "N/A"

            rows_html.append(
                f'<tr style="border-top:1px solid {BORDER};">'
                f'<td style="padding:9px 14px; color:{TEXT_PRIMARY}; '
                f'font-size:13px;">{c.label}</td>'
                f'<td style="padding:9px 14px; color:{TEXT_MUTED}; '
                f'font-size:11px;">{c.detail}</td>'
                f'<td style="padding:9px 14px; text-align:center; width:80px;">'
                f'<span style="display:inline-block; padding:3px 10px; '
                f'background:{bg}; color:{color}; border-radius:4px; '
                f'font-size:11px; font-weight:600; '
                f'border:1px solid {color};">{icon} {label}</span>'
                f'</td></tr>'
            )

        st.markdown(
            f'<table style="width:100%; border-collapse:collapse; '
            f'background:{SURFACE}; border:1px solid {BORDER}; '
            f'border-radius:6px; overflow:hidden; margin-bottom:6px;">'
            + "".join(rows_html) + "</table>",
            unsafe_allow_html=True,
        )
