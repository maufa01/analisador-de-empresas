"""
Markets — home page.

Layout (top → bottom):
    1. Header  (label + market status + pre-market futures when closed)
    2. YIELDS strip (3M / 5Y / 10Y / 30Y + 10Y-5Y proxy spread)
    3. 4 USA index cards (active card = gold border)
    4. COMMODITIES & FX strip (Gold / Oil / Gas / DXY / BTC)
    5. Main index chart (with optional volume subplot) + period pills
    6. MARKET BREADTH (Adv vs Dec / Above 50MA / 52W H-L / McClellan proxy)
    7. SECTOR PERFORMANCE heatmap (11 GICS sectors)
    8. TOP MOVERS — universe + sort + sector pills, "All sectors"
       grouped view shows sparklines + per-sector stats + show-more

Internationals removed per earlier rollback. Sparkline column + sector-
stats header + show-more toggle land in the grouped view.
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
    get_sparkline_panel,
)
from ui.charts.sp500_chart import build_sp500_figure
from ui.components.commodities_strip import render_commodities_strip
from ui.components.index_card import render_index_card
from ui.components.market_breadth import render_market_breadth
from ui.components.market_status import render_status_live
from ui.components.movers_table import render_movers, render_movers_grouped
from ui.components.period_selector import render_period_selector, to_yf_period
from ui.components.header_metric import render_header_metric
from ui.components.premarket_futures import render_premarket_futures
from ui.components.yields_strip import render_yields_strip


# ============================================================
# Auto-refresh — page-level, every 60s
# ============================================================
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    st_autorefresh(interval=60_000, key="markets_refresh")
except ImportError:
    pass


# ============================================================
# 1 — Header (status + pre-market futures right side)
# ============================================================
header_l, header_r = st.columns([4, 1.6])
with header_l:
    st.markdown(
        '<div class="eq-section-label">MARKETS</div>',
        unsafe_allow_html=True,
    )
with header_r:
    render_status_live()
    render_premarket_futures()


# ============================================================
# 2 — Yields strip (Treasury curve)
# ============================================================
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
render_yields_strip()


# ============================================================
# 3 — 4 USA index cards (no per-card click button — chart picker below)
# ============================================================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
indices = get_indices()
active_symbol: str = st.session_state.get("active_index_symbol", "^GSPC")

USA_ROW: tuple[str, ...] = ("^GSPC", "^IXIC", "^DJI", "^VIX")
cols = st.columns(len(USA_ROW))
for col, sym in zip(cols, USA_ROW):
    data = indices.get(sym, {})
    with col:
        # selectable=False: removed the "Show on chart" button per spec.
        # The chart-index selector below the chart handles selection.
        render_index_card(
            label=data.get("name", sym),
            last=data.get("last"),
            change_abs=data.get("change_abs"),
            change_pct=data.get("change_pct"),
            is_active=(sym == active_symbol),
            selectable=False,
        )

if all(v.get("last") is None for v in indices.values()):
    st.info(
        "No se pudieron cargar los datos de mercado. "
        "Intentá de nuevo en unos segundos.",
        icon="⚠",
    )


# ============================================================
# 4 — Commodities & FX strip
# ============================================================
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
render_commodities_strip()


# ============================================================
# 5 — Main chart + index picker
# ============================================================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

chart_l, chart_r = st.columns([3, 1])
with chart_l:
    # Tiny dropdown replaces the per-card "Show on chart" buttons
    pick_options = list(USA_ROW)
    pick_labels = [INDEX_META.get(s, {}).get("name", s) for s in pick_options]
    chosen_label = st.selectbox(
        "Display",
        options=pick_labels,
        index=pick_options.index(active_symbol)
              if active_symbol in pick_options else 0,
        label_visibility="collapsed",
    )
    chosen_symbol = pick_options[pick_labels.index(chosen_label)]
    if chosen_symbol != active_symbol:
        st.session_state["active_index_symbol"] = chosen_symbol
        active_symbol = chosen_symbol
        st.rerun()
with chart_r:
    period_label = render_period_selector(
        options=("1D", "1M", "1Y", "5Y"),
        default="1Y",
        key=f"period_{active_symbol}",
    )

active = indices.get(active_symbol, {})
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

history = get_index_history(active_symbol, period=to_yf_period(period_label))
fig = build_sp500_figure(history, height=380, show_volume=True)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ============================================================
# 6 — Market breadth
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="eq-section-label">MARKET BREADTH</div>',
    unsafe_allow_html=True,
)
render_market_breadth()


# ============================================================
# 7 — Top movers
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
        index=0, horizontal=True, label_visibility="collapsed",
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
        horizontal=True, label_visibility="collapsed",
        key="movers_sector",
    )
    st.markdown("</div>", unsafe_allow_html=True)

sort_key = {
    "Gainers":     "gainers",
    "Losers":      "losers",
    "Most active": "most_active",
}[sort_label]
universe_tickers = tickers_in(universe)


def _collect_sparkline_tickers(*frames) -> list[str]:
    out: set[str] = set()
    for f in frames:
        if f is None or f.empty or "ticker" not in f.columns:
            continue
        out.update(t for t in f["ticker"].tolist() if isinstance(t, str))
    return list(out)


if sector_choice == "All sectors":
    # Show top 5 per sector by default; the show-more button expands to
    # the full per_sector=25 slice. We pre-fetch BOTH so toggling is
    # instant (single yfinance hit per render).
    groups_top = get_movers_by_sector(
        universe=universe_tickers, per_sector=5, sort_by=sort_key,
    )
    groups_full = get_movers_by_sector(
        universe=universe_tickers, per_sector=25, sort_by=sort_key,
    )

    spark_tickers = _collect_sparkline_tickers(
        *groups_top.values(), *groups_full.values(),
    )
    sparklines = (get_sparkline_panel(tuple(spark_tickers), days=30)
                  if spark_tickers else {})

    render_movers_grouped(
        groups_top,
        sparklines=sparklines,
        full_groups=groups_full,
    )
else:
    df = get_movers(
        universe=universe_tickers, sort_by=sort_key,
        sector=sector_choice, top_n=25,
    )
    spark_tickers = _collect_sparkline_tickers(df)
    sparklines = (get_sparkline_panel(tuple(spark_tickers), days=30)
                  if spark_tickers else {})
    render_movers(df, height=520, include_sector_column=False,
                  sparklines=sparklines)


# Footer note about deferred sections
st.caption(
    "Earnings calendar and macro-event calendar require a live FMP / "
    "Trading Economics endpoint that isn't wired yet — they land when "
    "the data layer comes online."
)
