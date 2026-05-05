"""
Segmented bar showing Equity / Debt weights.

Pure HTML — no Plotly overhead for a one-shot proportion visual. Each
segment is sized by ``flex-grow`` and labelled inline when its share is
≥ 8% of the bar (anything smaller becomes unreadable on narrow columns).
"""
from __future__ import annotations

import streamlit as st


def render_capital_structure_bar(
    *,
    weight_equity: float,
    weight_debt: float | None = None,
    height: int = 24,
) -> None:
    """
    Args:
        weight_equity: in [0, 1]
        weight_debt:   if None, computed as 1 − weight_equity
        height:        bar height in px
    """
    we = max(0.0, min(1.0, float(weight_equity)))
    wd = max(0.0, min(1.0, 1.0 - we if weight_debt is None else float(weight_debt)))

    # Normalise so segments add to 100% even if caller passed odd values
    total = we + wd
    if total <= 0:
        we, wd = 1.0, 0.0
    else:
        we, wd = we / total, wd / total

    eq_pct = round(we * 100, 1)
    dt_pct = round(wd * 100, 1)
    eq_label = f"E {eq_pct:.1f}%" if eq_pct >= 8 else ""
    dt_label = f"D {dt_pct:.1f}%" if dt_pct >= 8 else ""

    # Single-line HTML — multi-line indented strings hit the markdown
    # 4-space code-block trap and render the closing </div> literally.
    seg_style = (
        "display:flex; align-items:center; justify-content:center; "
        "font-size:11px; font-weight:500; letter-spacing:0.4px; "
        "color:var(--bg-primary); font-variant-numeric:tabular-nums;"
    )
    html = (
        f'<div style="display:flex; width:100%; height:{height}px; '
        'border-radius:6px; overflow:hidden; '
        'border:1px solid var(--border); margin-top:6px;">'
        f'<div style="flex:{we}; background:var(--accent); {seg_style}">{eq_label}</div>'
        f'<div style="flex:{wd}; background:var(--text-muted); {seg_style}">{dt_label}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
