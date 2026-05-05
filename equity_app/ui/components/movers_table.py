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
        "ticker", "name", "sector", "last", "change_pct",
        "beta", "vol_30d", "volume_fmt", "mcap_fmt",
    ) if c in display.columns]
    return display, cols_order, has_sector


def render_movers(
    df: pd.DataFrame,
    *,
    height: int = 360,
    use_container_width: bool = True,
    include_sector_column: bool = False,
) -> None:
    """
    Single flat table. Pass ``include_sector_column=False`` (default) when
    the caller has already filtered to one sector.
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

    st.dataframe(
        _styled(display, cols_order),
        column_config=_column_config(include_sector="sector" in cols_order),
        use_container_width=use_container_width,
        height=height, hide_index=True,
    )


def render_movers_grouped(
    groups: dict[str, pd.DataFrame],
    *,
    row_height: int = 220,
) -> None:
    """
    Render one uppercase header per sector, followed by that sector's
    top-N table. Empty sectors render a single muted line.
    """
    if not groups:
        st.markdown(
            '<div class="eq-card" style="text-align:center; color:var(--text-muted);">'
            'No movers in any sector right now.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    for sector, df in groups.items():
        st.markdown(
            f'<div class="eq-section-label" '
            f'style="color:var(--accent); margin-top:16px; margin-bottom:6px;">'
            f'{sector.upper()}</div>',
            unsafe_allow_html=True,
        )
        if df is None or df.empty:
            st.markdown(
                '<div style="color:var(--text-muted); font-size:12px; '
                'padding: 6px 0;">No movers in this sector.</div>',
                unsafe_allow_html=True,
            )
            continue
        render_movers(df, height=row_height, include_sector_column=False)


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
