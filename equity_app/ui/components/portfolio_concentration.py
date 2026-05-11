"""Portfolio concentration — HHI + effective N + top-3/top-5."""
from __future__ import annotations

import streamlit as st


def _hhi_color(hhi: float) -> str:
    """Color chip based on HHI buckets (sum-of-squares of weights)."""
    if hhi < 0.10:
        return "var(--gains)"
    if hhi < 0.20:
        return "var(--accent)"
    return "rgba(184,115,51,1)"  # muted copper


def render_concentration(weights: dict[str, float]) -> None:
    if not weights:
        st.info("No weights provided for concentration analysis.")
        return

    # Normalise just in case caller passed % instead of decimals
    total = sum(weights.values())
    if total <= 0:
        st.info("Weights must sum to a positive value.")
        return
    norm = {t: w / total for t, w in weights.items()}

    sorted_w = sorted(norm.values(), reverse=True)
    hhi = sum(w * w for w in sorted_w)
    eff_n = (1.0 / hhi) if hhi > 0 else float("nan")
    top3 = sum(sorted_w[:3]) * 100.0
    top5 = sum(sorted_w[:5]) * 100.0

    color = _hhi_color(hhi)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f'<div data-testid="stMetric">'
        f'<div style="color:var(--text-muted); font-size:11px; '
        f'letter-spacing:0.6px; text-transform:uppercase;">HHI</div>'
        f'<div style="color:{color}; font-size:24px; font-weight:500; '
        f'letter-spacing:-0.3px; margin-top:2px;">{hhi:.3f}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    c2.metric("Effective N", f"{eff_n:.1f}")
    c3.metric("Top-3", f"{top3:.1f}%")
    c4.metric("Top-5", f"{top5:.1f}%")

    st.caption(
        "HHI: scaled 0-1. Below 0.10 = well-diversified; above 0.20 = "
        "highly concentrated. Effective N is what HHI would imply if "
        "all positions were equal-weighted."
    )
