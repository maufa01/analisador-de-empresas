"""
Provider Health dashboard.

Smoke-tests the 3 data providers (FMP, yfinance, Finnhub) for one
ticker and shows per-provider status + latency + sample fields. Useful
for the "the app suddenly broke" scenario — first click here, in 5
seconds you know which provider is down and why.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from core.provider_status import ProviderResult, ProviderStatus
from analysis.data_adapter import (
    _info_from_fmp, _info_from_yfinance, _info_from_finnhub,
    _price_from_fmp, _price_from_yfinance, _price_from_finnhub,
)
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"


# ============================================================
# Render helpers
# ============================================================
def _result_card(r: ProviderResult, *, extra: str = "") -> None:
    color = GAINS if r.is_ok else _DOWNSIDE
    glyph = "✓" if r.is_ok else "✗"
    latency = f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "—"
    extra_html = (f'<span style="color:{TEXT_SECONDARY}; font-weight:400; '
                  f'margin-left:8px;">{extra}</span>') if extra else ""
    st.markdown(
        f'<div style="background:{SURFACE}; border-left:3px solid {color}; '
        f'padding:12px 16px; border-radius:6px; margin-bottom:8px;">'
        f'<div style="display:flex; justify-content:space-between; '
        f'align-items:baseline;">'
        f'<span style="color:{color}; font-weight:500; font-size:14px;">'
        f'{glyph} {r.provider}{extra_html}</span>'
        f'<span style="color:{TEXT_MUTED}; font-size:11px;">'
        f'{r.status.value} · {latency}</span>'
        f'</div>'
        f'<div style="color:{TEXT_SECONDARY}; font-size:12px; margin-top:6px;">'
        f'{r.message or "—"}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Header
# ============================================================
st.markdown(
    '<div class="eq-section-label">PROVIDER HEALTH</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Smoke-test the 3 data providers against a known ticker. "
    "If yfinance is consistently scrape_blocked, Yahoo changed their "
    "backend — FMP must carry the load."
)

c1, c2, c3, _ = st.columns([2, 1, 1, 3])
with c1:
    test_ticker = st.text_input(
        "Test ticker", value="AAPL",
        label_visibility="collapsed",
        placeholder="Ticker (e.g. AAPL)",
    ).upper().strip()
with c2:
    run_clicked = st.button("Run health check", type="primary",
                             use_container_width=True)
with c3:
    if st.button("Clear cache", use_container_width=True,
                 help="Wipe all @st.cache_data entries. Use after a "
                      "code change or when the app shows stale errors."):
        st.cache_data.clear()
        st.success("Cache cleared. Reload the app to refetch.")


# ============================================================
# Results
# ============================================================
if run_clicked and test_ticker:
    # ---- Company info chain ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'COMPANY INFO CHAIN · FMP → yfinance → Finnhub</div>',
        unsafe_allow_html=True,
    )
    with st.spinner("Running info chain…"):
        info_results = [
            _info_from_fmp(test_ticker),
            _info_from_yfinance(test_ticker),
            _info_from_finnhub(test_ticker),
        ]
    for r in info_results:
        extra = ""
        if r.is_ok and r.data:
            name = r.data.get("name") or "—"
            extra = f"→ {name}"
        _result_card(r, extra=extra)
        if r.is_ok and r.data:
            with st.expander(f"Sample fields from {r.provider}"):
                preview = {k: v for k, v in list(r.data.items())[:10]
                           if v is not None}
                st.json(preview)

    # ---- Price chain ----
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'PRICE CHAIN · FMP → Finnhub → yfinance</div>',
        unsafe_allow_html=True,
    )
    with st.spinner("Running price chain…"):
        price_results = [
            _price_from_fmp(test_ticker),
            _price_from_finnhub(test_ticker),
            _price_from_yfinance(test_ticker),
        ]
    for r in price_results:
        extra = ""
        if r.is_ok and r.data:
            extra = f"→ ${r.data.get('price', 0):.2f}"
        _result_card(r, extra=extra)

    # ---- Verdict ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    info_ok = any(r.is_ok for r in info_results)
    price_ok = any(r.is_ok for r in price_results)

    if info_ok and price_ok:
        st.success("✓ Both chains healthy — the app should work.")
    elif info_ok:
        st.warning(
            "⚠ Price chain partially broken. Live quotes may be stale "
            "or missing."
        )
    elif price_ok:
        st.warning(
            "⚠ Info chain broken. Company profiles will fail; valuation "
            "tabs will mostly render empty."
        )
    else:
        st.error(
            "✗ Both chains down — the app cannot function for this "
            "ticker. Check FMP_API_KEY first; that's the most likely "
            "single cause."
        )

    # ---- Status summary table ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">STATUS SUMMARY</div>',
        unsafe_allow_html=True,
    )
    rows = []
    for r in info_results:
        rows.append({"chain": "info", "provider": r.provider,
                     "status": r.status.value,
                     "latency_ms": (f"{r.latency_ms:.0f}"
                                    if r.latency_ms is not None else "—"),
                     "message": r.message or "—"})
    for r in price_results:
        rows.append({"chain": "price", "provider": r.provider,
                     "status": r.status.value,
                     "latency_ms": (f"{r.latency_ms:.0f}"
                                    if r.latency_ms is not None else "—"),
                     "message": r.message or "—"})
    import pandas as pd
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)
