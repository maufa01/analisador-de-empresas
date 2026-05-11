"""3-mode portfolio input widget for the Portfolio page.

Modes:
- Preset:   pick a themed basket + dollar value → auto-generate shares
- Custom:   multiselect tickers + per-ticker shares/cost editors
- Raw text: vanilla TICKER,SHARES,COST_BASIS textarea (legacy)

Returns the holdings as raw text in the same TICKER,SHARES,COST_BASIS
format the downstream parser expects, so the rest of the page wiring
is unchanged.
"""
from __future__ import annotations
from typing import Optional

import math
import streamlit as st

from data.portfolio_presets import PORTFOLIO_PRESETS
from data.ticker_universe import SP500_TOP


# ============================================================
# Live-price helpers (yfinance-first, FMP fallback)
# ============================================================
@st.cache_data(ttl=3_600, show_spinner=False)
def _get_current_price(ticker: str) -> Optional[float]:
    """Best-effort current price. None if both providers fail."""
    # yfinance fast_info — primary path
    try:
        from data.market_data import _yfinance
        yf = _yfinance()
        if yf is not None:
            info = yf.Ticker(ticker).fast_info
            for key in ("last_price", "lastPrice", "regular_market_price",
                        "regularMarketPrice"):
                v = None
                try:
                    v = info[key] if key in info else getattr(info, key, None)
                except (KeyError, TypeError):
                    v = getattr(info, key, None)
                if v is not None:
                    try:
                        p = float(v)
                        if p > 0:
                            return p
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass
    # FMP fallback — fetch_quote
    try:
        from data.fmp_provider import FMPProvider
        prov = FMPProvider()
        q = prov.fetch_quote(ticker)
        if q and q.price and q.price > 0:
            return float(q.price)
    except Exception:
        pass
    return None


def _price_or(ticker: str, default: float = 100.0) -> float:
    p = _get_current_price(ticker)
    return p if (p is not None and p > 0) else default


# ============================================================
# Mode renderers
# ============================================================
def _render_preset_mode(default_text: str) -> str:
    """Pick a themed basket + total $ → auto-generate holdings text."""
    col1, col2 = st.columns([2, 1])
    preset_name = col1.selectbox(
        "Theme", list(PORTFOLIO_PRESETS.keys()),
        key="portfolio_preset_name",
    )
    portfolio_value = col2.number_input(
        "Portfolio value ($)",
        value=100_000, min_value=1_000, step=10_000,
        key="portfolio_preset_value",
    )
    preset = PORTFOLIO_PRESETS.get(preset_name, {})
    if preset.get("description"):
        st.caption(preset["description"])

    if st.button("Generate holdings", key="portfolio_preset_generate"):
        tickers = preset.get("tickers", [])
        if not tickers:
            st.warning("Preset has no tickers — choose another.")
            return st.session_state.get("portfolio_holdings_text", default_text)
        per_position = float(portfolio_value) / len(tickers)
        lines: list[str] = []
        missing: list[str] = []
        with st.spinner(f"Fetching prices for {len(tickers)} tickers…"):
            for tkr in tickers:
                price = _get_current_price(tkr)
                if price is None or price <= 0:
                    missing.append(tkr)
                    continue
                shares = math.floor(per_position / price)
                if shares <= 0:
                    missing.append(tkr)
                    continue
                lines.append(f"{tkr},{shares},{price:.2f}")
        if not lines:
            st.error("Could not fetch any prices for this preset.")
            return st.session_state.get("portfolio_holdings_text", default_text)
        if missing:
            st.warning(f"Skipped (no price): {', '.join(missing)}")
        text = "\n".join(lines)
        st.session_state["portfolio_holdings_text"] = text

    return st.session_state.get("portfolio_holdings_text", default_text)


def _render_custom_mode(default_text: str) -> str:
    """Multiselect tickers + per-row shares/cost editors."""
    # Build label list "TICKER — Name" for nicer multiselect search
    options = list(SP500_TOP.keys())
    label_map = {t: f"{t} — {SP500_TOP[t]}" for t in options}

    selected = st.multiselect(
        "Pick tickers (max 20)",
        options=options,
        max_selections=20,
        format_func=lambda t: label_map.get(t, t),
        key="portfolio_custom_tickers",
    )

    if selected:
        st.caption(
            f"Editing {len(selected)} positions. Cost basis defaults to "
            "current price — overwrite if you have a real buy price."
        )
        # Per-ticker editor rows
        for tkr in selected:
            default_price = _price_or(tkr, 100.0)
            col_a, col_b = st.columns(2)
            col_a.number_input(
                f"{tkr} shares", value=10, min_value=0,
                step=1, key=f"portfolio_custom_sh_{tkr}",
            )
            col_b.number_input(
                f"{tkr} cost basis", value=float(default_price),
                min_value=0.0, step=1.0, format="%.2f",
                key=f"portfolio_custom_cb_{tkr}",
            )

        if st.button("Generate holdings", key="portfolio_custom_generate"):
            lines: list[str] = []
            for tkr in selected:
                shares = st.session_state.get(f"portfolio_custom_sh_{tkr}", 0)
                cost = st.session_state.get(f"portfolio_custom_cb_{tkr}", 0.0)
                if shares > 0 and cost > 0:
                    lines.append(f"{tkr},{int(shares)},{float(cost):.2f}")
            if lines:
                st.session_state["portfolio_holdings_text"] = "\n".join(lines)
            else:
                st.warning("No positions with shares > 0 and cost > 0.")

    return st.session_state.get("portfolio_holdings_text", default_text)


def _render_raw_text_mode(default_text: str) -> str:
    """Legacy textarea — same UX the page started with."""
    text = st.text_area(
        "Holdings (one per line: TICKER,SHARES,COST_BASIS)",
        value=st.session_state.get("portfolio_holdings_text", default_text),
        height=200,
        key="portfolio_raw_text",
    )
    if text:
        st.session_state["portfolio_holdings_text"] = text
    return text


# ============================================================
# Public API
# ============================================================
def render_portfolio_input(
    *,
    default_text: str = "AAPL,100,150.0\nMSFT,50,300.0\nGOOG,20,140.0",
) -> str:
    """Render the 3-mode input widget. Returns the holdings text in
    the legacy TICKER,SHARES,COST_BASIS format."""
    mode = st.radio(
        "Input mode",
        options=["Preset", "Custom", "Raw text"],
        horizontal=True,
        key="portfolio_input_mode",
    )

    if mode == "Preset":
        return _render_preset_mode(default_text)
    if mode == "Custom":
        return _render_custom_mode(default_text)
    return _render_raw_text_mode(default_text)
