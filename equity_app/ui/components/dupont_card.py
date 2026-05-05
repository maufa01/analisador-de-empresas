"""
DuPont decomposition card.

ROE = Net Margin × Asset Turnover × Equity Multiplier

Three boxes joined by ``×`` separators, with the resulting ROE on the
right after an ``=`` separator. All HTML emitted as one single-line
string so st.markdown's indented-code-block trap doesn't apply.
"""
from __future__ import annotations
from typing import Optional

import math
import pandas as pd
import streamlit as st

from analysis.ratios import _get


def _last(s: Optional[pd.Series]) -> Optional[float]:
    if s is None:
        return None
    clean = s.dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    try:
        out = a / b
    except ZeroDivisionError:
        return None
    if not math.isfinite(out):
        return None
    return out


def compute_dupont(
    income: pd.DataFrame, balance: pd.DataFrame
) -> dict[str, Optional[float]]:
    """Returns the three drivers + the ROE that recombines them."""
    ni = _last(_get(income, "net_income"))
    rev = _last(_get(income, "revenue"))
    assets = _last(_get(balance, "total_assets"))
    equity = _last(_get(balance, "total_equity"))

    net_margin = _safe_div(ni, rev)
    asset_turn = _safe_div(rev, assets)
    eq_mult    = _safe_div(assets, equity)
    roe = (
        net_margin * asset_turn * eq_mult
        if (net_margin is not None and asset_turn is not None
            and eq_mult is not None) else None
    )
    return {
        "net_margin":  net_margin,
        "asset_turn":  asset_turn,
        "eq_mult":     eq_mult,
        "roe":         roe,
    }


# ============================================================
# Render
# ============================================================
def _box(value: Optional[float], label: str, *, suffix: str = "", is_result: bool = False) -> str:
    if value is None:
        text = "—"
        color = "var(--text-muted)"
    else:
        if suffix == "%":
            text = f"{value * 100:.2f}%"
        elif suffix == "x":
            text = f"{value:.2f}x"
        else:
            text = f"{value:.2f}"
        color = "var(--accent)" if is_result else "var(--text-primary)"

    border = "2px solid var(--accent)" if is_result else "1px solid var(--border)"
    bg = "var(--surface)" if not is_result else "var(--surface-raised)"
    return (
        f'<div style="flex:1; min-width:120px; background:{bg}; '
        f'border:{border}; border-radius:8px; padding:14px 12px; text-align:center;">'
        f'<div style="font-size:24px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">{text}</div>'
        f'<div class="eq-idx-label" style="margin-top:4px;">{label}</div>'
        '</div>'
    )


def _connector(symbol: str) -> str:
    return (
        f'<div style="display:flex; align-items:center; justify-content:center; '
        f'min-width:24px; color:var(--text-muted); font-size:18px; '
        f'font-weight:500;">{symbol}</div>'
    )


def render_dupont_card(income: pd.DataFrame, balance: pd.DataFrame) -> None:
    drivers = compute_dupont(income, balance)
    html = (
        '<div class="eq-card" style="padding:18px;">'
        '<div class="eq-section-label" style="margin-bottom:10px;">'
        'DUPONT DECOMPOSITION · ROE = NET MARGIN × ASSET TURNOVER × EQUITY MULTIPLIER'
        '</div>'
        '<div style="display:flex; flex-wrap:wrap; gap:8px; align-items:stretch;">'
        + _box(drivers["net_margin"], "NET MARGIN", suffix="%")
        + _connector("×")
        + _box(drivers["asset_turn"], "ASSET TURNOVER", suffix="x")
        + _connector("×")
        + _box(drivers["eq_mult"],    "EQUITY MULTIPLIER", suffix="x")
        + _connector("=")
        + _box(drivers["roe"],        "RETURN ON EQUITY", suffix="%", is_result=True)
        + '</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
