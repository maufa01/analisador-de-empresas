"""Top movers table — st.dataframe with column_config and conditional colors."""
from __future__ import annotations
from typing import Sequence

import pandas as pd
import streamlit as st

from ui.theme import GAINS, LOSSES


def _compact_volume(v: float) -> str:
    if v is None or pd.isna(v):
        return "—"
    if v >= 1e9:  return f"{v/1e9:.2f}B"
    if v >= 1e6:  return f"{v/1e6:.1f}M"
    if v >= 1e3:  return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"


def render_movers(
    df: pd.DataFrame,
    *,
    height: int = 360,
    use_container_width: bool = True,
) -> None:
    """
    Expects columns: ticker, name, last, change_pct, beta, vol_30d, volume.

    Renders a styled dataframe with tabular-nums (the global CSS handles
    that) and column_config for currency / percent / compact volume.
    """
    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="text-align:center; color:var(--text-muted);">'
            'No movers available — try again in a few seconds.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    display = df.copy()
    if "volume" in display.columns:
        display["volume_fmt"] = display["volume"].apply(_compact_volume)

    cols_order: list[str] = [c for c in (
        "ticker", "name", "last", "change_pct", "beta", "vol_30d", "volume_fmt",
    ) if c in display.columns]

    column_config = {
        "ticker":     st.column_config.TextColumn("Ticker",     width="small"),
        "name":       st.column_config.TextColumn("Name",       width="medium"),
        "last":       st.column_config.NumberColumn("Last",       format="$%.2f", width="small"),
        "change_pct": st.column_config.NumberColumn("Change",     format="%.2f%%", width="small"),
        "beta":       st.column_config.NumberColumn("Beta",       format="%.2f",  width="small"),
        "vol_30d":    st.column_config.NumberColumn("Vol 30d",    format="%.1f%%", width="small"),
        "volume_fmt": st.column_config.TextColumn("Volume",      width="small"),
    }

    # Conditional row color via Styler (applies only to change_pct column)
    def _color_change(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ""
        if f > 0:
            return f"color: {GAINS};"
        if f < 0:
            return f"color: {LOSSES};"
        return ""

    # ``Styler.applymap`` was removed in pandas 2.2 — use ``Styler.map``
    # when available and fall back to applymap on older versions.
    subset = ["change_pct"] if "change_pct" in cols_order else []
    styler = display[cols_order].style
    apply_fn = getattr(styler, "map", None) or styler.applymap
    styled = apply_fn(_color_change, subset=subset)

    st.dataframe(
        styled,
        column_config=column_config,
        use_container_width=use_container_width,
        height=height,
        hide_index=True,
    )


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
