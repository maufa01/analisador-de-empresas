"""
Market breadth — 4 cards (Advancers vs Decliners · Above 50-day MA ·
52-week highs vs lows · McClellan-style oscillator proxy).

Source: ``data.market_data.get_market_breadth`` over the curated 119-
ticker S&P universe (running breadth on the full 500 names is too slow
for a yfinance-backed page).
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from data.market_data import get_market_breadth


def _interpret(value: Optional[float], thresholds: tuple[float, float]) -> tuple[str, str]:
    """Returns (label, css color var) given two threshold cuts."""
    if value is None:
        return "—", "var(--text-muted)"
    bear, bull = thresholds
    if value >= bull:
        return "Bullish", "var(--gains)"
    if value <= bear:
        return "Bearish", "var(--losses)"
    return "Neutral", "var(--accent)"


def _bar_html(left: float, right: float) -> str:
    """A dual-segment bar showing left vs right share. Both are counts."""
    total = max(left + right, 1.0)
    l_pct = left / total * 100
    r_pct = right / total * 100
    return (
        '<div style="display:flex; height:6px; border-radius:3px; overflow:hidden; '
        'background:var(--surface-raised); margin-top:8px;">'
        f'<div style="width:{l_pct}%; background:var(--gains);"></div>'
        f'<div style="width:{r_pct}%; background:var(--losses);"></div>'
        '</div>'
    )


def _ma_bar_html(pct: Optional[float]) -> str:
    if pct is None:
        return ''
    fill = max(0.0, min(100.0, pct))
    color = ("var(--gains)" if fill > 60
             else "var(--accent)" if fill > 40
             else "var(--losses)")
    return (
        '<div style="height:6px; border-radius:3px; overflow:hidden; '
        'background:var(--surface-raised); margin-top:8px;">'
        f'<div style="width:{fill}%; height:100%; background:{color};"></div>'
        '</div>'
    )


def render_market_breadth() -> None:
    b = get_market_breadth()

    adv = b.get("advancing")
    dec = b.get("declining")
    pct_ma = b.get("pct_above_50ma")
    nh = b.get("new_52w_highs")
    nl = b.get("new_52w_lows")
    mcc = b.get("mcclellan_proxy")

    # Card 1 — Advancers vs Decliners
    adv_dec_label, adv_dec_color = _interpret(
        (adv - dec) if (adv is not None and dec is not None) else None,
        thresholds=(-20, 20),
    )
    card1 = (
        '<div class="eq-card" style="padding:14px 16px;">'
        '<div class="eq-idx-label">ADVANCING vs DECLINING</div>'
        f'<div style="display:flex; align-items:baseline; gap:6px; margin-top:4px;">'
        f'<span style="color:var(--gains); font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{int(adv) if adv is not None else "—"}</span>'
        f'<span style="color:var(--text-muted);">/</span>'
        f'<span style="color:var(--losses); font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{int(dec) if dec is not None else "—"}</span>'
        '</div>'
        + (_bar_html(adv, dec) if (adv is not None and dec is not None) else '')
        + f'<div style="color:{adv_dec_color}; font-size:11px; '
          f'margin-top:6px; letter-spacing:0.4px;">{adv_dec_label}</div>'
          '</div>'
    )

    # Card 2 — % above 50-day MA
    ma_label, ma_color = _interpret(pct_ma, thresholds=(35, 65))
    pct_ma_text = f"{pct_ma:.1f}%" if pct_ma is not None else "—"
    card2 = (
        '<div class="eq-card" style="padding:14px 16px;">'
        '<div class="eq-idx-label">ABOVE 50-DAY MA</div>'
        f'<div style="color:var(--text-primary); font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">{pct_ma_text}</div>'
        + _ma_bar_html(pct_ma)
        + f'<div style="color:{ma_color}; font-size:11px; '
          f'margin-top:6px; letter-spacing:0.4px;">{ma_label}</div>'
          '</div>'
    )

    # Card 3 — 52W highs vs lows
    nh_dec_diff = ((nh or 0) - (nl or 0)) if (nh is not None or nl is not None) else None
    nh_label, nh_color = _interpret(nh_dec_diff, thresholds=(-3, 3))
    card3 = (
        '<div class="eq-card" style="padding:14px 16px;">'
        '<div class="eq-idx-label">NEW 52W HIGHS vs LOWS</div>'
        f'<div style="display:flex; align-items:baseline; gap:6px; margin-top:4px;">'
        f'<span style="color:var(--gains); font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{int(nh) if nh is not None else "—"}</span>'
        f'<span style="color:var(--text-muted);">/</span>'
        f'<span style="color:var(--losses); font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{int(nl) if nl is not None else "—"}</span>'
        '</div>'
        + (_bar_html(nh or 0, nl or 0) if (nh is not None or nl is not None) else '')
        + f'<div style="color:{nh_color}; font-size:11px; '
          f'margin-top:6px; letter-spacing:0.4px;">{nh_label}</div>'
          '</div>'
    )

    # Card 4 — McClellan-style proxy
    mcc_label, mcc_color = _interpret(mcc, thresholds=(-30, 30))
    mcc_text = f"{mcc:+.0f}" if mcc is not None else "—"
    card4 = (
        '<div class="eq-card" style="padding:14px 16px;">'
        '<div class="eq-idx-label">McCLELLAN PROXY</div>'
        f'<div style="color:{mcc_color}; font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">{mcc_text}</div>'
        '<div style="color:var(--text-muted); font-size:11px; margin-top:6px;">'
        '(Adv − Dec) / Total ×100'
        '</div>'
        f'<div style="color:{mcc_color}; font-size:11px; '
        f'margin-top:6px; letter-spacing:0.4px;">{mcc_label}</div>'
        '</div>'
    )

    cols = st.columns(4, gap="small")
    cols[0].markdown(card1, unsafe_allow_html=True)
    cols[1].markdown(card2, unsafe_allow_html=True)
    cols[2].markdown(card3, unsafe_allow_html=True)
    cols[3].markdown(card4, unsafe_allow_html=True)
