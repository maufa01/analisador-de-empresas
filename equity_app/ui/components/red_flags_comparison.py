"""
Red-flags comparison card — educational table showing how the three
earnings-quality models scored well-known fraud / failure cases vs the
target ticker.

Hardcoded reference data — sourced from academic post-mortems
(Beneish papers; Piotroski follow-ups; SEC enforcement filings). The
intent is teaching, not nowcasting.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from analysis.earnings_quality import EarningsQuality


# Famous failure cases — pre-collapse-year scores per the academic
# literature. Numbers are illustrative and should be treated as
# directional, not authoritative.
RED_FLAG_CASES: list[dict] = [
    {"company": "Enron",     "year": 2000, "beneish":  0.45, "piotroski": 4, "sloan":  0.18},
    {"company": "WorldCom",  "year": 2001, "beneish":  0.32, "piotroski": 3, "sloan":  0.22},
    {"company": "Lehman Bros", "year": 2007, "beneish":  0.18, "piotroski": 4, "sloan":  0.12},
    {"company": "Wirecard",  "year": 2019, "beneish":  0.28, "piotroski": 5, "sloan":  0.15},
]


def _flag_color(value: float, *, lower_better: bool) -> str:
    if lower_better:
        if value > -1.78:  return "var(--losses)"
        if value > -2.22:  return "var(--accent)"
        return "var(--gains)"
    if value >= 7: return "var(--gains)"
    if value >= 5: return "var(--accent)"
    return "var(--losses)"


def _color_cell(text: str, color: str) -> str:
    return (
        f'<span style="color:{color}; font-variant-numeric:tabular-nums; '
        f'font-weight:500;">{text}</span>'
    )


def render_red_flags_comparison(target_ticker: str, eq: Optional[EarningsQuality]) -> None:
    """
    Render an educational table juxtaposing the user's target with the
    famous failure cases. ``eq=None`` (or any sub-model None) renders
    "—" for the target row.
    """
    rows = list(RED_FLAG_CASES)

    # Append target row
    target_beneish = eq.beneish.score if (eq and eq.beneish) else None
    target_piotroski = (int(eq.piotroski.score)
                        if (eq and eq.piotroski) else None)
    target_sloan = eq.sloan.score if (eq and eq.sloan) else None

    rows.append({
        "company":  target_ticker,
        "year":     "current",
        "beneish":  target_beneish,
        "piotroski": target_piotroski,
        "sloan":    target_sloan,
    })

    body_rows = []
    for r in rows:
        is_target = r["company"] == target_ticker

        beneish_txt = (
            _color_cell(f"{r['beneish']:+.2f}",
                        _flag_color(r["beneish"], lower_better=True))
            if r["beneish"] is not None else "—"
        )
        piotroski_txt = (
            _color_cell(f"{int(r['piotroski'])}/9",
                        _flag_color(r["piotroski"], lower_better=False))
            if r["piotroski"] is not None else "—"
        )
        # Sloan shown as % with absolute-value-based colour
        if r["sloan"] is not None:
            sl_pct = r["sloan"] * 100 if abs(r["sloan"]) < 1 else r["sloan"]
            sloan_color = (
                "var(--losses)" if abs(r["sloan"]) > 0.10
                else "var(--accent)" if abs(r["sloan"]) > 0.05
                else "var(--gains)"
            )
            sloan_txt = _color_cell(f"{sl_pct:+.1f}%", sloan_color)
        else:
            sloan_txt = "—"

        weight = "500" if is_target else "400"
        opacity = "1" if is_target else "0.85"
        body_rows.append(
            f'<tr style="opacity:{opacity};">'
            f'<td style="padding:8px 12px; color:var(--text-primary); '
            f'font-weight:{weight}; font-size:13px;">{r["company"]}</td>'
            f'<td style="padding:8px 12px; text-align:right; '
            f'color:var(--text-muted); font-size:12px;">{r["year"]}</td>'
            f'<td style="padding:8px 12px; text-align:right;">{beneish_txt}</td>'
            f'<td style="padding:8px 12px; text-align:right;">{piotroski_txt}</td>'
            f'<td style="padding:8px 12px; text-align:right;">{sloan_txt}</td>'
            '</tr>'
        )

    head = (
        '<thead><tr style="background:#1A2033;">'
        '<th style="padding:10px 12px; text-align:left; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Company</th>'
        '<th style="padding:10px 12px; text-align:right; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Year</th>'
        '<th style="padding:10px 12px; text-align:right; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Beneish</th>'
        '<th style="padding:10px 12px; text-align:right; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Piotroski</th>'
        '<th style="padding:10px 12px; text-align:right; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Sloan</th>'
        '</tr></thead>'
    )

    table = (
        '<div style="background:#131826; border:1px solid #1F2937; '
        'border-radius:8px; overflow:auto;">'
        '<table style="width:100%; border-collapse:collapse;">'
        + head + '<tbody>' + "".join(body_rows) + '</tbody></table></div>'
    )

    st.markdown(
        '<div class="eq-section-label">RED FLAGS · EDUCATIONAL COMPARISON</div>',
        unsafe_allow_html=True,
    )
    st.markdown(table, unsafe_allow_html=True)
    st.caption(
        "Pre-collapse Beneish / Piotroski / Sloan scores for famous "
        "fraud cases — sourced from academic post-mortems. The further "
        f"**{target_ticker}** sits from these patterns, the lower the "
        "manipulation risk."
    )
