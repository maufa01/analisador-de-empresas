"""Markets — home page. Indices grid + S&P chart + top movers."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from data.market_data import (
    INDEX_TICKERS,
    get_indices,
    get_movers,
    get_spx_history,
)
from ui.components.index_card import render_index_card
from ui.components.market_status import render_status_live
from ui.components.movers_table import render_movers
from ui.components.period_selector import render_period_selector, to_yf_period
from ui.components.header_metric import render_header_metric
from ui.charts.sp500_chart import build_sp500_figure


# ============================================================
# Auto-refresh — page-level, every 60s
# ============================================================
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    st_autorefresh(interval=60_000, key="markets_refresh")
except ImportError:
    pass


# ============================================================
# Header row — title + market status
# ============================================================
header_l, header_r = st.columns([4, 1])
with header_l:
    st.markdown(
        '<div class="eq-section-label">MARKETS</div>',
        unsafe_allow_html=True,
    )
with header_r:
    render_status_live()


# ============================================================
# Index cards
# ============================================================
indices = get_indices()

cols = st.columns(len(INDEX_TICKERS))
for col, label in zip(cols, INDEX_TICKERS.keys()):
    data = indices.get(label, {})
    with col:
        render_index_card(
            label=label,
            last=data.get("last"),
            change_abs=data.get("change_abs"),
            change_pct=data.get("change_pct"),
        )

# Empty-state message if every index failed
if all(v.get("last") is None for v in indices.values()):
    st.info(
        "No se pudieron cargar los datos de mercado. "
        "Intentá de nuevo en unos segundos.",
        icon="⚠",
    )


# ============================================================
# S&P chart card
# ============================================================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

with st.container():
    chart_l, chart_r = st.columns([3, 1])
    spx = indices.get("S&P 500", {})

    with chart_l:
        # Header inside chart card
        last = spx.get("last")
        change_pct = spx.get("change_pct")
        ytd_str = (
            f"{'+' if (change_pct or 0) >= 0 else ''}{change_pct:.2f}% YTD"
            if change_pct is not None else ""
        )
        render_header_metric(
            label="S&P 500 · LAST 12 MONTHS",
            value=f"{last:,.2f}" if last is not None else "—",
            delta=ytd_str if ytd_str else None,
            delta_positive=(change_pct or 0) >= 0 if change_pct is not None else None,
        )

    with chart_r:
        period_label = render_period_selector(
            options=("1D", "1M", "1Y", "5Y"),
            default="1Y",
            key="spx_period",
        )

    history = get_spx_history(to_yf_period(period_label))
    fig = build_sp500_figure(history, height=320)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ============================================================
# Top movers
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

mv_l, mv_r = st.columns([3, 2])
with mv_l:
    st.markdown(
        '<div class="eq-section-label">TOP MOVERS · S&P 500</div>',
        unsafe_allow_html=True,
    )
with mv_r:
    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    sel = st.radio(
        "movers_sort",
        options=["Gainers", "Losers", "Most active"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="mv_sort",
    )
    st.markdown("</div>", unsafe_allow_html=True)

sort_key = {"Gainers": "gainers", "Losers": "losers", "Most active": "most_active"}[sel]
movers = get_movers(sort_by=sort_key, top_n=10)
render_movers(movers, height=380)
