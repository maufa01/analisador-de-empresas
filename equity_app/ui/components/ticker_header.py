"""
Big ticker header — three-column layout:
    LEFT  : ticker + company name + sector + market cap
    MID   : current price + daily change + 52w range
    RIGHT : aggregator intrinsic + upside + rating verdict + confidence

Uses ``st.metric`` for the price/intrinsic so the values render cleanly
on every Streamlit version (the previous custom-HTML cards started
showing literal ``</div>`` after a Streamlit Cloud upgrade).
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from scoring.rating import Rating


_VERDICT_COLOR = {
    "STRONG BUY":  "var(--gains)",
    "BUY":         "var(--gains)",
    "HOLD":        "var(--accent)",
    "SELL":        "var(--losses)",
    "STRONG SELL": "var(--losses)",
}


def _fmt_money_short(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1e12: return f"${v/1e12:,.2f}T"
    if av >= 1e9:  return f"${v/1e9:,.2f}B"
    if av >= 1e6:  return f"${v/1e6:,.1f}M"
    if av >= 1e3:  return f"${v/1e3:,.1f}K"
    return f"${v:,.2f}"


def render_ticker_header(
    *,
    ticker: str,
    company_name: str,
    sector: Optional[str],
    market_cap: Optional[float],
    current_price: Optional[float],
    daily_change_pct: Optional[float] = None,
    week52_low: Optional[float] = None,
    week52_high: Optional[float] = None,
    intrinsic: Optional[float],
    upside: Optional[float],
    rating: Optional[Rating] = None,
    confidence: Optional[str] = None,
    range_p25: Optional[float] = None,
    range_p75: Optional[float] = None,
    clipped_models: Optional[list[str]] = None,
) -> None:
    """
    Render the big top-of-page header. Pass ``rating=None`` if the
    pipeline hasn't run yet — the right column will show "—" for the
    verdict instead of erroring.
    """
    left, mid, right = st.columns([2.2, 2.2, 2.6])

    # ----- LEFT: identity -----
    with left:
        st.markdown(
            f'<div class="eq-section-label" style="color:var(--accent);">'
            f'{ticker}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:var(--text-primary); font-size:18px; '
            f'font-weight:500; margin-top:2px; line-height:1.3;">'
            f'{company_name}</div>',
            unsafe_allow_html=True,
        )
        meta_bits = []
        if sector:
            meta_bits.append(sector)
        if market_cap is not None:
            meta_bits.append(f"Mkt cap {_fmt_money_short(market_cap)}")
        if meta_bits:
            st.markdown(
                f'<div style="color:var(--text-muted); font-size:12px; '
                f'margin-top:4px;">{" · ".join(meta_bits)}</div>',
                unsafe_allow_html=True,
            )

    # ----- MID: price -----
    with mid:
        delta_str = (f"{daily_change_pct:+.2f}% today"
                     if daily_change_pct is not None else None)
        st.metric(
            label="CURRENT PRICE",
            value=(f"${current_price:,.2f}"
                   if current_price is not None else "—"),
            delta=delta_str,
        )
        if week52_low is not None and week52_high is not None:
            st.markdown(
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:-6px; letter-spacing:0.4px;">'
                f'52W RANGE  ${week52_low:,.2f} – ${week52_high:,.2f}</div>',
                unsafe_allow_html=True,
            )

    # ----- RIGHT: intrinsic + rating -----
    with right:
        upside_delta = (f"{upside*100:+.1f}% vs price"
                        if upside is not None else None)
        st.metric(
            label="AGGREGATOR INTRINSIC",
            value=(f"${intrinsic:,.2f}"
                   if intrinsic is not None else "—"),
            delta=upside_delta,
        )

        # Range subtitle (when aggregator provides p25-p75)
        if (range_p25 is not None and range_p75 is not None
                and range_p25 == range_p25 and range_p75 == range_p75):
            st.markdown(
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:-6px; letter-spacing:0.4px;">'
                f'RANGE  ${range_p25:,.0f} – ${range_p75:,.0f}</div>',
                unsafe_allow_html=True,
            )

        # Action label: price-vs-range when range is available, else the
        # rating engine's verdict (back-compat for callers not passing
        # a range yet).
        verdict: Optional[str] = None
        color: str = "var(--accent)"
        if (current_price is not None and range_p25 is not None
                and range_p75 is not None
                and range_p25 == range_p25 and range_p75 == range_p75):
            if current_price < range_p25:
                verdict, color = "BUY", "var(--gains)"
            elif current_price > range_p75:
                verdict, color = "SELL", "var(--losses)"
            else:
                verdict, color = "FAIR VALUE", "var(--text-muted)"
        elif rating is not None:
            verdict = rating.verdict
            color = _VERDICT_COLOR.get(rating.verdict, "var(--accent)")

        if verdict is not None:
            conf_raw = (confidence or (rating.confidence if rating else None) or "")
            conf = conf_raw.upper() if isinstance(conf_raw, str) else ""
            conf_color = {
                "HIGH":   "var(--gains)",
                "MEDIUM": "var(--accent)",
                "LOW":    "var(--losses)",
            }.get(conf, "var(--text-muted)")
            conf_html = (
                f'<span style="color:var(--text-muted); font-size:11px; '
                f'letter-spacing:0.4px;">CONFIDENCE '
                f'<b style="color:{conf_color};">{conf}</b></span>'
            ) if conf else ""
            st.markdown(
                f'<div style="display:flex; align-items:baseline; gap:10px; '
                f'margin-top:-4px;">'
                f'<span style="color:{color}; font-weight:500; '
                f'font-size:18px; letter-spacing:0.3px;">{verdict}</span>'
                f'{conf_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Clipped-models caption — only when sanity clip excluded anything
        if clipped_models:
            st.caption(
                f"Models excluded (>60% off price): {', '.join(clipped_models)}"
            )
