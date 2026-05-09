"""
Render forensic flags as a stacked card list.

Each flag shows severity glyph + label + a one-line numeric detail.
"All clear" state when nothing fired.
"""
from __future__ import annotations
from typing import Iterable

import streamlit as st

from analysis.forensics import ForensicFlag


_GLYPH = {
    "critical": "✗",
    "warning":  "⚠",
    "info":     "ⓘ",
}

_COLOR = {
    "critical": "#DC2626",
    "warning":  "rgba(184,115,51,1)",      # _DOWNSIDE
    "info":     "#9CA3AF",
}


def render_forensic_flags(flags: Iterable[ForensicFlag]) -> None:
    """Render a sequence of :class:`ForensicFlag` as a stacked card list.
    Empty input renders an "all clear" success banner."""
    flags = list(flags or [])

    st.markdown(
        '<div class="eq-section-label">FORENSIC FLAGS</div>',
        unsafe_allow_html=True,
    )

    if not flags:
        st.markdown(
            '<div style="background:var(--surface); border-left:3px solid '
            '#10B981; padding:14px 18px; border-radius:6px; '
            'color:var(--text-secondary); font-size:13px;">'
            '<span style="color:#10B981; font-weight:600;">✓ All clear</span> '
            ' — no forensic rule fired on the current financials.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Sort: critical first, then warning, then info — visual triage order
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    sorted_flags = sorted(flags, key=lambda f: severity_rank.get(f.severity, 9))

    rows = []
    for f in sorted_flags:
        glyph = _GLYPH.get(f.severity, "?")
        color = _COLOR.get(f.severity, "#9CA3AF")
        rows.append(
            f'<div style="background:var(--surface); border-left:3px solid '
            f'{color}; padding:10px 14px; border-radius:6px; '
            f'margin-bottom:6px;">'
            f'<div style="display:flex; align-items:baseline; gap:10px;">'
            f'<span style="color:{color}; font-weight:600; font-size:14px;">'
            f'{glyph}</span>'
            f'<span style="color:var(--text-primary); font-weight:500; '
            f'font-size:13px;">{f.label}</span>'
            f'<span style="color:var(--text-muted); font-size:11px; '
            f'text-transform:uppercase; letter-spacing:0.5px; '
            f'margin-left:auto;">{f.category}</span>'
            f'</div>'
            f'<div style="color:var(--text-secondary); font-size:12px; '
            f'margin-top:4px; line-height:1.4;">{f.detail}</div>'
            f'</div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)

    # Tally row
    n_crit = sum(1 for f in flags if f.severity == "critical")
    n_warn = sum(1 for f in flags if f.severity == "warning")
    n_info = sum(1 for f in flags if f.severity == "info")
    st.caption(
        f"{len(flags)} flag(s) — {n_crit} critical, "
        f"{n_warn} warning, {n_info} info."
    )
