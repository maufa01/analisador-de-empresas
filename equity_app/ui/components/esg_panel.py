"""
ESG scores panel — Sustainalytics-style total + E/S/G subscores from
Finnhub's /stock/esg endpoint.

Finnhub returns:
    {
      'totalEsg': float,
      'environmentScore': float,
      'socialScore': float,
      'governanceScore': float,
      'ratingYear': int,
      'ratingMonth': int,
      ...
    }

Lower is better in Sustainalytics' framework (lower risk score). We
surface the convention explicitly so users don't misread "high score"
as "good ESG".
"""
from __future__ import annotations
from typing import Optional

import streamlit as st


def _fmt_score(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "—"


def render_esg_panel(ticker: str) -> None:
    try:
        from data.finnhub_provider import is_available, fetch_esg_scores
    except Exception:
        return
    if not is_available():
        return

    try:
        esg = fetch_esg_scores(ticker) or {}
    except Exception:
        return
    if not esg:
        return

    total = esg.get("totalEsg")
    env = esg.get("environmentScore")
    soc = esg.get("socialScore")
    gov = esg.get("governanceScore")

    # Don't waste a section on a totally-empty payload
    if not any(isinstance(v, (int, float)) for v in (total, env, soc, gov)):
        return

    # Lower-is-better: a "category" colour helps users orient quickly.
    if isinstance(total, (int, float)):
        if total < 20:
            color = "var(--gains)"
            verdict = "Low risk"
        elif total < 30:
            color = "var(--accent)"
            verdict = "Medium risk"
        else:
            color = "rgba(184,115,51,1)"
            verdict = "High risk"
    else:
        color = "var(--text-muted)"
        verdict = "—"

    rating_year = esg.get("ratingYear")
    rating_month = esg.get("ratingMonth")
    asof = ""
    if rating_year and rating_month:
        asof = f"as-of {int(rating_month):02d}/{int(rating_year)}"

    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color}; margin-top:14px;">'
        '<div class="eq-section-label">ESG · FINNHUB / SUSTAINALYTICS</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:28px; font-weight:500; letter-spacing:-0.4px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{_fmt_score(total)}</span>'
        f'<span style="color:{color}; font-weight:500; letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:13px;">{verdict}</span>'
        + (f'<span style="color:var(--text-muted); font-size:12px;">'
           f'· {asof}</span>' if asof else "")
        + '</div>'
        '<div style="margin-top:6px; color:var(--text-muted); font-size:11px;">'
        'Lower scores = lower ESG risk (Sustainalytics convention).'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="small")
    c1.metric("ENVIRONMENT", _fmt_score(env))
    c2.metric("SOCIAL", _fmt_score(soc))
    c3.metric("GOVERNANCE", _fmt_score(gov))
