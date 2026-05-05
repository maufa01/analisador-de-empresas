"""
Earnings-quality detailed cards — three side-by-side score cards
(Beneish · Piotroski · Sloan) + an overall composite header.

Each card:
    - Big tabular score
    - Flag pill (GREEN / YELLOW / RED) with interpretation text
    - Threshold reference
    - Expander with the per-component breakdown table

Reads from ``analysis.earnings_quality.EarningsQuality``. Single-line
HTML throughout to dodge the markdown indented-code-block trap.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from analysis.earnings_quality import EarningsQuality, QualityFlag


_FLAG_COLOR = {
    "green":  "var(--gains)",
    "yellow": "var(--accent)",
    "red":    "var(--losses)",
    "unknown": "var(--text-muted)",
}


def _composite_score(eq: EarningsQuality) -> int:
    """Weighted 0-100 composite across the 3 sub-models."""
    weighted = 0.0

    if eq.beneish:
        if eq.beneish.flag == "green":  weighted += 35
        elif eq.beneish.flag == "yellow": weighted += 20

    if eq.piotroski:
        # Piotroski.score is 0-9
        weighted += min(eq.piotroski.score / 9.0, 1.0) * 35

    if eq.sloan:
        if eq.sloan.flag == "green":  weighted += 30
        elif eq.sloan.flag == "yellow": weighted += 15

    return int(round(weighted))


def _composite_color(score: int) -> str:
    if score >= 75: return "var(--gains)"
    if score >= 50: return "var(--accent)"
    return "var(--losses)"


# ============================================================
# Single-card renderer
# ============================================================
def _card_html(
    *,
    title: str,
    main_value: str,
    flag: str,
    interpretation: str,
    threshold_text: str,
) -> str:
    color = _FLAG_COLOR.get(flag.lower(), "var(--text-muted)")
    return (
        '<div class="eq-card" style="padding:18px 20px; '
        f'border-left:3px solid {color}; min-height:200px;">'
        f'<div class="eq-idx-label">{title}</div>'
        f'<div style="font-size:30px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums; margin-top:6px;">'
        f'{main_value}</div>'
        '<div style="height:1px; background:var(--border); margin:12px 0;"></div>'
        f'<div style="color:{color}; font-size:11px; font-weight:500; '
        f'letter-spacing:0.4px; text-transform:uppercase; margin-bottom:6px;">'
        f'{flag.upper()}</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'line-height:1.5; margin-bottom:8px;">{interpretation}</div>'
        f'<div style="color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.3px;">{threshold_text}</div>'
        '</div>'
    )


def _beneish_card(qf: Optional[QualityFlag]) -> tuple[str, Optional[QualityFlag]]:
    if qf is None:
        return _card_html(
            title="BENEISH M-SCORE", main_value="—",
            flag="unknown",
            interpretation="Beneish M-Score could not be computed for this period.",
            threshold_text="Threshold: M > -1.78 ⇒ manipulation risk",
        ), None
    return _card_html(
        title="BENEISH M-SCORE",
        main_value=f"{qf.score:.2f}",
        flag=qf.flag,
        interpretation=qf.explanation,
        threshold_text="Threshold: M > -1.78 ⇒ high manipulation risk",
    ), qf


def _piotroski_card(qf: Optional[QualityFlag]) -> tuple[str, Optional[QualityFlag]]:
    if qf is None:
        return _card_html(
            title="PIOTROSKI F-SCORE", main_value="—",
            flag="unknown",
            interpretation="F-Score could not be computed.",
            threshold_text="0-3 weak · 4-6 average · 7-9 strong",
        ), None
    return _card_html(
        title="PIOTROSKI F-SCORE",
        main_value=f"{int(qf.score)} / 9",
        flag=qf.flag,
        interpretation=qf.explanation,
        threshold_text="0-3 weak · 4-6 average · 7-9 strong",
    ), qf


def _sloan_card(qf: Optional[QualityFlag]) -> tuple[str, Optional[QualityFlag]]:
    if qf is None:
        return _card_html(
            title="SLOAN RATIO", main_value="—",
            flag="unknown",
            interpretation="Sloan ratio could not be computed.",
            threshold_text="|Sloan| > 0.10 ⇒ low earnings quality",
        ), None
    pct = qf.score * 100
    return _card_html(
        title="SLOAN RATIO",
        main_value=f"{pct:+.2f}%",
        flag=qf.flag,
        interpretation=qf.explanation,
        threshold_text="|Sloan| > 10% ⇒ low earnings quality",
    ), qf


def _components_table(qf: QualityFlag) -> pd.DataFrame:
    rows = []
    for k, v in qf.components.items():
        if isinstance(v, bool):
            rows.append({"Component": k, "Value": "✓" if v else "✗"})
        elif isinstance(v, (int, float)):
            rows.append({"Component": k, "Value": f"{v:,.4f}"
                         if abs(v) < 1 else f"{v:,.3f}"})
        else:
            rows.append({"Component": k, "Value": str(v)})
    return pd.DataFrame(rows)


# ============================================================
# Public API
# ============================================================
def render_earnings_quality_detail(eq: EarningsQuality) -> None:
    """Render the composite header + 3 detailed cards + breakdowns."""
    composite = _composite_score(eq)
    color = _composite_color(composite)
    flag_label = (
        "GREEN" if composite >= 75
        else "YELLOW" if composite >= 50
        else "RED"
    )

    # Composite header
    st.markdown(
        '<div class="eq-card" '
        f'style="padding:18px 22px; border-left:4px solid {color};">'
        '<div class="eq-idx-label">EARNINGS QUALITY · COMPOSITE</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:36px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{composite}/100</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{flag_label}</span>'
        '</div>'
        '<div style="margin-top:8px; color:var(--text-muted); '
        'font-size:12px; line-height:1.5;">'
        'Weighted blend: Beneish (35%) + Piotroski (35%) + Sloan (30%). '
        'Sub-models triangulate manipulation risk, fundamental strength, '
        'and accruals quality.'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # 3 score cards
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    col_b, col_p, col_s = st.columns(3, gap="medium")

    b_html, b_flag = _beneish_card(eq.beneish)
    p_html, p_flag = _piotroski_card(eq.piotroski)
    s_html, s_flag = _sloan_card(eq.sloan)

    with col_b:
        st.markdown(b_html, unsafe_allow_html=True)
    with col_p:
        st.markdown(p_html, unsafe_allow_html=True)
    with col_s:
        st.markdown(s_html, unsafe_allow_html=True)

    # Per-card breakdowns
    if b_flag and b_flag.components:
        with st.expander("Beneish breakdown (8 variables)", expanded=False):
            st.dataframe(
                _components_table(b_flag),
                hide_index=True, use_container_width=True,
            )
            st.caption(
                "DSRI = Days-Sales-Receivables Index · GMI = Gross-Margin Index · "
                "AQI = Asset-Quality Index · SGI = Sales-Growth Index · "
                "DEPI = Depreciation Index · SGAI = SG&A Index · "
                "LVGI = Leverage Index · TATA = Total Accruals / Total Assets."
            )

    if p_flag and p_flag.components:
        with st.expander("Piotroski breakdown (9 binary checks)", expanded=False):
            st.dataframe(
                _components_table(p_flag),
                hide_index=True, use_container_width=True,
            )

    if s_flag and s_flag.components:
        with st.expander("Sloan breakdown", expanded=False):
            st.dataframe(
                _components_table(s_flag),
                hide_index=True, use_container_width=True,
            )
            st.caption(
                "Sloan ratio = (Net Income − Operating Cash Flow) / "
                "Average Total Assets. Negative values mean cash flow runs "
                "ahead of reported earnings — high quality."
            )
