"""Top movers table — st.dataframe with column_config and conditional colors.

Two render modes:
- ``render_movers``           — single flat table (filtered to one sector
                                or universe-wide depending on caller).
- ``render_movers_grouped``   — used in "All sectors" view; takes a
                                ``{sector: DataFrame}`` dict and renders
                                a uppercase header per sector + the table.
"""
from __future__ import annotations
from typing import Sequence

import pandas as pd
import streamlit as st

from ui.theme import GAINS, LOSSES


def _compact_volume(v: float) -> str:
    if v is None or pd.isna(v):
        return "—"
    if v >= 1e12: return f"{v/1e12:.2f}T"
    if v >= 1e9:  return f"{v/1e9:.2f}B"
    if v >= 1e6:  return f"{v/1e6:.1f}M"
    if v >= 1e3:  return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"


def _styled(display: pd.DataFrame, cols_order: list[str]):
    """Build the conditional-color Styler for the change_pct column."""
    def _color_change(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ""
        if f > 0:  return f"color: {GAINS};"
        if f < 0:  return f"color: {LOSSES};"
        return ""

    subset = ["change_pct"] if "change_pct" in cols_order else []
    styler = display[cols_order].style
    apply_fn = getattr(styler, "map", None) or styler.applymap
    return apply_fn(_color_change, subset=subset)


def _column_config(include_sector: bool) -> dict:
    cfg = {
        "ticker":     st.column_config.TextColumn("Ticker",   width="small"),
        "name":       st.column_config.TextColumn("Name",     width="medium"),
        "last":       st.column_config.NumberColumn("Last",     format="$%.2f", width="small"),
        "change_pct": st.column_config.NumberColumn("Change",   format="%.2f%%", width="small"),
        "beta":       st.column_config.NumberColumn("Beta",     format="%.2f", width="small"),
        "vol_30d":    st.column_config.NumberColumn("Vol 30d",  format="%.1f%%", width="small"),
        "volume_fmt": st.column_config.TextColumn("Volume",    width="small"),
        "mcap_fmt":   st.column_config.TextColumn("Market cap", width="small"),
    }
    if include_sector:
        cfg["sector"] = st.column_config.TextColumn("Sector", width="medium")
    return cfg


def _prep_display(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], bool]:
    display = df.copy()
    if "volume" in display.columns:
        display["volume_fmt"] = display["volume"].apply(_compact_volume)
    if "market_cap" in display.columns:
        display["mcap_fmt"] = display["market_cap"].apply(_compact_volume)
    has_sector = "sector" in display.columns and display["sector"].notna().any()
    cols_order = [c for c in (
        "ticker", "name", "sector", "spark", "last", "change_pct",
        "beta", "vol_30d", "volume_fmt", "mcap_fmt",
    ) if c in display.columns]
    return display, cols_order, has_sector


def _column_config_full(include_sector: bool, include_spark: bool) -> dict:
    cfg = _column_config(include_sector=include_sector)
    if include_spark:
        cfg["spark"] = st.column_config.LineChartColumn(
            "1M trend", width="small",
            help="Last 30 trading days of close prices.",
        )
    return cfg


def render_movers(
    df: pd.DataFrame,
    *,
    height: int = 360,
    use_container_width: bool = True,
    include_sector_column: bool = False,
    sparklines: dict[str, list[float]] | None = None,
) -> None:
    """
    Single flat table. Pass ``include_sector_column=False`` (default) when
    the caller has already filtered to one sector. ``sparklines`` is an
    optional ``{ticker: [close_t0, ...]}`` mapping; when provided, a
    LineChartColumn is added between Name and Last.
    """
    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="text-align:center; color:var(--text-muted);">'
            'No movers in this slice.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    display, cols_order, has_sector = _prep_display(df)
    if not include_sector_column and "sector" in cols_order:
        cols_order = [c for c in cols_order if c != "sector"]

    if sparklines:
        display["spark"] = display["ticker"].map(
            lambda t: sparklines.get(t, []) or [],
        )
    elif "spark" in cols_order:
        cols_order = [c for c in cols_order if c != "spark"]

    # Styler dropped because LineChartColumn doesn't compose with the
    # change_pct conditional colour. The dark theme already tints the
    # change column appropriately via the format spec.
    st.dataframe(
        display[cols_order] if not sparklines else display[cols_order],
        column_config=_column_config_full(
            include_sector="sector" in cols_order,
            include_spark="spark" in cols_order,
        ),
        use_container_width=use_container_width,
        height=height, hide_index=True,
    )


def _render_sector_stats_header(
    sector: str,
    df: pd.DataFrame,
    *,
    full_panel: pd.DataFrame | None = None,
) -> None:
    """One-line stats above each sector's table — return / mkt cap / up/down."""
    if df is None or df.empty:
        return
    # Stats from the full sector slice when provided (the caller's `df`
    # may already be a top-N; full_panel keeps the full sector for stats)
    stats_src = full_panel if (full_panel is not None and not full_panel.empty) else df
    avg_chg = float(stats_src["change_pct"].mean()) if "change_pct" in stats_src.columns else None
    n_up = int((stats_src["change_pct"] > 0).sum()) if "change_pct" in stats_src.columns else None
    n_down = int((stats_src["change_pct"] < 0).sum()) if "change_pct" in stats_src.columns else None
    mc_total = (float(stats_src["market_cap"].sum()) if "market_cap" in stats_src.columns
                else None)

    chg_html = ""
    if avg_chg is not None:
        sign = "+" if avg_chg >= 0 else ""
        color = "var(--gains)" if avg_chg >= 0 else "var(--losses)"
        chg_html = (f'<span style="color:{color}; font-size:13px; '
                    f'font-variant-numeric:tabular-nums;">'
                    f'{sign}{avg_chg:.2f}% avg</span>')

    mc_html = ""
    if mc_total is not None and mc_total > 0:
        mc_html = (f' &nbsp; · &nbsp; <span style="color:var(--text-muted); '
                   f'font-size:12px;">total cap '
                   f'<b style="color:var(--text-secondary); '
                   f'font-variant-numeric:tabular-nums;">'
                   f'{_compact_volume(mc_total)}</b></span>')

    counts_html = ""
    if n_up is not None and n_down is not None:
        counts_html = (
            f' &nbsp; · &nbsp; <span style="color:var(--gains); font-size:12px;">'
            f'▲ {n_up}</span><span style="color:var(--text-muted);"> / </span>'
            f'<span style="color:var(--losses); font-size:12px;">▼ {n_down}</span>'
        )

    st.markdown(
        f'<div style="display:flex; justify-content:space-between; '
        f'align-items:baseline; margin-top:14px; margin-bottom:4px;">'
        f'<span class="eq-section-label" style="color:var(--accent);">'
        f'{sector.upper()}</span>'
        f'<span>{chg_html}{mc_html}{counts_html}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_movers_grouped(
    groups: dict[str, pd.DataFrame],
    *,
    row_height: int = 220,
    sparklines: dict[str, list[float]] | None = None,
    expanded_sector_state_key: str = "movers_expanded_sectors",
    full_groups: dict[str, pd.DataFrame] | None = None,
) -> None:
    """
    Render one stats header + table per sector. ``sparklines`` is the
    same {ticker: prices} mapping used by ``render_movers``. When the
    user clicks "Show 20 more" for a sector, the renderer reads the
    full slice from ``full_groups`` (caller-provided) and the toggle
    state from session_state[expanded_sector_state_key].
    """
    if not groups:
        st.markdown(
            '<div class="eq-card" style="text-align:center; color:var(--text-muted);">'
            'No movers in any sector right now.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    expanded: set[str] = st.session_state.setdefault(expanded_sector_state_key, set())
    full_groups = full_groups or {}

    for sector, df in groups.items():
        full = full_groups.get(sector, df)
        _render_sector_stats_header(sector, df, full_panel=full)
        if df is None or df.empty:
            st.markdown(
                '<div style="color:var(--text-muted); font-size:12px; '
                'padding: 6px 0;">No movers in this sector.</div>',
                unsafe_allow_html=True,
            )
            continue

        is_expanded = sector in expanded
        view = full if is_expanded else df
        render_movers(view, height=row_height, include_sector_column=False,
                      sparklines=sparklines)

        # Show-more toggle when there's actually more to show
        if full is not None and len(full) > len(df):
            label = (f"Show fewer ({len(df)})" if is_expanded
                     else f"Show {len(full) - len(df)} more")
            if st.button(label, key=f"showmore_{sector}",
                         type="secondary"):
                if is_expanded:
                    expanded.discard(sector)
                else:
                    expanded.add(sector)
                st.rerun()


def render_mover_tabs(
    sources: dict[str, pd.DataFrame],
    *,
    default: str = "Gainers",
) -> None:
    """Pill switch for Gainers / Losers / Most active."""
    keys = list(sources.keys())
    if default not in keys and keys:
        default = keys[0]

    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    sel = st.radio(
        "movers_view",
        options=keys, index=keys.index(default),
        horizontal=True, label_visibility="collapsed",
        key="movers_pill",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    render_movers(sources[sel])


def render_mover_tabs(
    sources: dict[str, pd.DataFrame],
    *,
    default: str = "Gainers",
) -> None:
    """Pill switch for Gainers / Losers / Most active."""
    keys = list(sources.keys())
    if default not in keys and keys:
        default = keys[0]

    st.markdown('<div class="eq-pills">', unsafe_allow_html=True)
    sel = st.radio(
        "movers_view",
        options=keys,
        index=keys.index(default),
        horizontal=True,
        label_visibility="collapsed",
        key="movers_pill",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    render_movers(sources[sel])
