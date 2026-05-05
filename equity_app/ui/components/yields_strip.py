"""
Yields strip — one-line summary of the Treasury curve (3M / 5Y / 10Y / 30Y)
plus the 2s10s spread (proxied as 5Y-vs-10Y when 2Y isn't available).

Goes red when the curve is inverted (proxy < 0).
"""
from __future__ import annotations

import streamlit as st

from data.market_data import get_yields


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%"


def _fmt_bps(v: float | None) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.0f}bps"


def render_yields_strip() -> None:
    yields = get_yields()
    if not any(yields.get(t, {}).get("last_pct") is not None
               for t in yields):
        st.caption("Yield-curve data unavailable — yfinance returned empty.")
        return

    chunks: list[str] = []
    for tenor in ("3M", "5Y", "10Y", "30Y"):
        d = yields.get(tenor, {})
        last = _fmt_pct(d.get("last_pct"))
        chg = d.get("change_bps_5d")
        chg_html = (f' <span style="color:var(--text-muted); font-size:11px;">'
                    f'({_fmt_bps(chg)})</span>' if chg is not None else "")
        chunks.append(
            f'<span style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.4px;">{tenor}</span> '
            f'<b style="color:var(--text-primary); '
            f'font-variant-numeric:tabular-nums;">{last}</b>{chg_html}'
        )

    # 2s10s proxy: 10Y − 5Y (true 2s10s would need ^IRX or ZF=F)
    spread_bps = None
    spread_color = "var(--text-secondary)"
    y10 = yields.get("10Y", {}).get("last_pct")
    y5  = yields.get("5Y", {}).get("last_pct")
    if y10 is not None and y5 is not None:
        spread_bps = (y10 - y5) * 100.0
        spread_color = ("var(--losses)" if spread_bps < 0
                        else "var(--text-primary)")
    spread_text = (f'{spread_bps:+.0f}bps' if spread_bps is not None else "—")

    body = " &nbsp; · &nbsp; ".join(chunks)
    body += (
        f' &nbsp; · &nbsp; '
        f'<span style="color:var(--text-muted); font-size:11px;">10Y-5Y</span> '
        f'<b style="color:{spread_color}; font-variant-numeric:tabular-nums;">'
        f'{spread_text}</b>'
    )

    st.markdown(
        '<div class="eq-card" style="padding:10px 16px;">'
        '<span class="eq-section-label" style="margin-right:14px;">YIELDS</span>'
        + body +
        '</div>',
        unsafe_allow_html=True,
    )
