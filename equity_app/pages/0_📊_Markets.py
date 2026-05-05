"""
Markets — home page.

Layout (top → bottom):
    1. Header label + live market-status pill (right-aligned)
    2. ONE row of 4 USA index cards (S&P 500 · Nasdaq · Dow · VIX)
       — clicking a card swaps the chart below; the active card carries
       a 2px gold border.
    3. Main index chart with subtle period pills (1D / 1M / 1Y / 5Y).
    4. Sector performance heatmap (11 SPDR sector ETFs) + a row of
       click-to-filter buttons under it.
    5. Top movers — universe + sort + sector pills, with an
       "All sectors" grouped view that lists 5 names per sector.

International indices and the "Index Explorer" pill selector were
removed per the rollback request — only the 4 USA benchmarks remain.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from data.constituents import SECTORS, UNIVERSES, tickers_in
from data.market_data import (
    INDEX_META,
    get_indices, get_index_history,
    get_movers, get_movers_by_sector,
    get_sector_performance,
)
from ui.charts.sp500_chart import build_sp500_figure
from ui.components.index_card import render_index_card
from ui.components.market_status import render_status_live
from ui.components.movers_table import render_movers, render_movers_grouped
from ui.components.period_selector import render_period_selector, to_yf_period
from ui.components.header_metric import render_header_metric
from ui.components.sector_heatmap import render_sector_heatmap


# ============================================================
# Auto-refresh — page-level, every 60s
# ============================================================
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    st_autorefresh(interval=60_000, key="markets_refresh")
except ImportError:
    pass


# ============================================================
# 1 — Header
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
# 2 — 4 USA index cards (one row). Clicking swaps the chart.
# ============================================================
indices = get_indices()
active_symbol: str = st.session_state.get("active_index_symbol", "^GSPC")


def _set_active(sym: str) -> None:
    st.session_state["active_index_symbol"] = sym


USA_ROW: tuple[str, ...] = ("^GSPC", "^IXIC", "^DJI", "^VIX")

cols = st.columns(len(USA_ROW))
for col, sym in zip(cols, USA_ROW):
    data = indices.get(sym, {})
    with col:
        render_index_card(
            label=data.get("name", sym),
            last=data.get("last"),
            change_abs=data.get("change_abs"),
            change_pct=data.get("change_pct"),
            is_active=(sym == active_symbol),
            selectable=True,
            symbol=sym,
            on_select=_set_active,
        )

if all(v.get("last") is None for v in indices.values()):
    st.info(
        "No se pudieron cargar los datos de mercado. "
        "Intentá de nuevo en unos segundos.",
        icon="⚠",
    )


# ============================================================
# 3 — Main index chart
# ============================================================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

chart_l, chart_r = st.columns([3, 1])
active = indices.get(active_symbol, {})

with chart_l:
    last = active.get("last")
    change_pct = active.get("change_pct")
    ytd_str = (
        f"{'+' if (change_pct or 0) >= 0 else ''}{change_pct:.2f}% YTD"
        if change_pct is not None else ""
    )
    render_header_metric(
        label=f"{active.get('name', active_symbol).upper()} · LAST 12 MONTHS",
        value=f"{last:,.2f}" if last is not None else "—",
        delta=ytd_str if ytd_str else None,
        delta_positive=(change_pct or 0) >= 0 if change_pct is not None else None,
    )

with chart_r:
    period_label = render_period_selector(
        options=("1D", "1M", "1Y", "5Y"),
        default="1Y",
        key=f"period_{active_symbol}",
    )

history = get_index_history(active_symbol, period=to_yf_period(period_label))
fig = build_sp500_figure(history, height=320)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ============================================================
# 4 — Sector performance heatmap
# ============================================================
st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">SECTOR PERFORMANCE</div>',
    unsafe_allow_html=True,
)

sectors_df = get_sector_performance()
render_sector_heatmap(sectors_df, height=240)


# ============================================================
# 5 — Top movers (universe + sort + sector segmentation)
# ============================================================
st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

mv_l, mv_r = st.columns([3, 2])
with mv_l:
    st.markdown(
        '<div class="eq-section-label">TOP MOVERS</div>',
        unsafe_allow_html=True,
    )
with mv_r:
    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    sort_label = st.radio(
        "movers_sort",
        options=["Gainers", "Losers", "Most active"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="movers_sort_pill",
    )
    st.markdown("</div>", unsafe_allow_html=True)

fl, fr = st.columns([1.2, 4])
with fl:
    universe = st.selectbox(
        "Universe", options=list(UNIVERSES.keys()),
        index=0, label_visibility="collapsed",
        key="movers_universe",
    )
with fr:
    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    sector_options = ["All sectors", *SECTORS]
    current_sector = st.session_state.get("movers_sector", "All sectors")
    if current_sector not in sector_options:
        current_sector = "All sectors"
    sector_choice = st.radio(
        "movers_sector_pill",
        options=sector_options,
        index=sector_options.index(current_sector),
        horizontal=True,
        label_visibility="collapsed",
        key="movers_sector",
    )
    st.markdown("</div>", unsafe_allow_html=True)

sort_key = {
    "Gainers":     "gainers",
    "Losers":      "losers",
    "Most active": "most_active",
}[sort_label]

universe_tickers = tickers_in(universe)

if sector_choice == "All sectors":
    groups = get_movers_by_sector(
        universe=universe_tickers, per_sector=5, sort_by=sort_key,
    )
    render_movers_grouped(groups)
else:
    df = get_movers(
        universe=universe_tickers, sort_by=sort_key,
        sector=sector_choice, top_n=25,
    )
    render_movers(df, height=480, include_sector_column=False)
