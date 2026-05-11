"""
Portfolio — paste-driven holdings + simple stress test.

Replaces the old multi-tab optimizer (P11.A2). For personal portfolios
with 5-20 holdings, the academic optimization methods (HRP, BL, GARCH)
were noise. This page does what the user actually does:

1. Paste holdings (TICKER,SHARES[,COST_BASIS]).
2. See positions + weights + unrealized P/L.
3. Move a market-shock slider, see the dollar impact.
4. Optional: 1-day historical VaR @ 95% via the preserved
   ``portfolio.var_calculator`` module.

Live prices via yfinance. No optimization, no backtest, no efficient
frontier — those modules were deleted (recoverable from git history if
you want them back).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st

from ui.components.portfolio_concentration import render_concentration
from ui.components.portfolio_sector_breakdown import render_sector_breakdown
from ui.components.portfolio_quality_screen import render_quality_screen
from ui.components.portfolio_correlation import render_correlation_heatmap
from ui.components.portfolio_risk_decomposition import render_risk_decomposition
from ui.components.portfolio_stress_tests import render_stress_tests
from ui.components.portfolio_markowitz import render_markowitz_frontier


@st.cache_data(ttl=21_600, show_spinner=False)
def _portfolio_returns(tickers: tuple[str, ...], period: str = "3y") -> pd.DataFrame:
    """Daily returns DataFrame (rows=dates, cols=tickers), cached 6h."""
    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame()
    try:
        df = yf.download(list(tickers), period=period,
                         auto_adjust=True, progress=False)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(name=tickers[0])
        return df.pct_change().dropna(how="all")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21_600, show_spinner=False)
def _bundles_for(tickers: tuple[str, ...]) -> dict:
    """Cached load_bundle per ticker — used by sector + quality components."""
    from analysis.parallel_loader import load_bundle
    out = {}
    for t in tickers:
        try:
            out[t] = load_bundle(t)
        except Exception:
            out[t] = None
    return out


# ============================================================
# Header
# ============================================================
st.markdown(
    '<div class="eq-section-label">PORTFOLIO</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Paste holdings, see positions + weights + P/L, stress against "
    "market shock. No optimization theatre — vanilla Markowitz + 5–20 "
    "holdings doesn't need it."
)


# ============================================================
# Holdings input
# ============================================================
DEFAULT_HOLDINGS = "AAPL,100,150.0\nMSFT,50,300.0\nGOOG,20,140.0"
holdings_input = st.text_area(
    "Holdings (one per line: TICKER,SHARES,COST_BASIS)",
    placeholder=DEFAULT_HOLDINGS,
    height=140,
    key="portfolio_holdings_input",
)

if not holdings_input.strip():
    st.info("Paste your holdings to begin (or use the placeholder format).")
    st.stop()


# ============================================================
# Parse + fetch live prices
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def _quote(ticker: str) -> float | None:
    try:
        import yfinance as yf
        fast = yf.Ticker(ticker).fast_info
        v = fast.get("lastPrice") if hasattr(fast, "get") else getattr(fast, "lastPrice", None)
        return float(v) if v else None
    except Exception:
        return None


def _parse_holdings(text: str) -> list[dict]:
    out: list[dict] = []
    for raw in text.strip().split("\n"):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        ticker = parts[0].upper()
        try:
            shares = float(parts[1])
        except ValueError:
            continue
        cost = None
        if len(parts) >= 3:
            try:
                cost = float(parts[2])
            except ValueError:
                cost = None
        price = _quote(ticker)
        if price is None or price <= 0:
            continue
        out.append({
            "ticker": ticker,
            "shares": shares,
            "cost":   cost,
            "price":  price,
            "value":  shares * price,
        })
    return out


with st.spinner("Fetching live prices…"):
    holdings = _parse_holdings(holdings_input)

if not holdings:
    st.error(
        "Could not fetch any prices. Check ticker spelling — yfinance may "
        "also be temporarily scrape-blocked (run the Health page to verify)."
    )
    st.stop()

total_value = sum(h["value"] for h in holdings)
df = pd.DataFrame(holdings)
df["weight_%"] = df["value"] / total_value * 100.0
if df["cost"].notna().any():
    df["pl_$"] = (df["price"] - df["cost"].fillna(0.0)) * df["shares"]
    total_pl = float(df["pl_$"].fillna(0.0).sum())
else:
    df["pl_$"] = float("nan")
    total_pl = 0.0


# ============================================================
# Summary cards
# ============================================================
c1, c2, c3 = st.columns(3)
c1.metric("Total value",   f"${total_value:,.0f}")
c2.metric("Positions",     len(holdings))
c3.metric("Unrealized P/L", f"${total_pl:+,.0f}")


# ============================================================
# Holdings table
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:14px;">HOLDINGS</div>',
    unsafe_allow_html=True,
)
display_df = df[["ticker", "shares", "cost", "price",
                 "value", "weight_%", "pl_$"]].copy()
display_df.columns = ["Ticker", "Shares", "Cost", "Price",
                      "Value", "Weight %", "P/L $"]
display_df = display_df.round(2)
st.dataframe(display_df, hide_index=True, use_container_width=True)


# ============================================================
# Load bundles (sector + financials per ticker) + returns once
# ============================================================
tickers_tuple = tuple(sorted(h["ticker"] for h in holdings))
# weight derived from value / total_value (raw holdings dict only has
# value, not weight_% — that column lives on df, not the list).
weights = {h["ticker"]: h["value"] / total_value for h in holdings}
current_prices = {h["ticker"]: h["price"] for h in holdings}

with st.spinner("Loading sector + fundamentals for each holding…"):
    bundles = _bundles_for(tickers_tuple)

# Build the holdings-meta dict used by sector + stress components
holdings_meta = {}
for h in holdings:
    tkr = h["ticker"]
    b = bundles.get(tkr)
    sector = getattr(b, "sector", None) if b is not None else None
    holdings_meta[tkr] = {
        "weight": h["value"] / total_value,
        "sector": sector,
        "value":  h["value"],
    }


# ============================================================
# Concentration · Sector breakdown · Quality screen
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">CONCENTRATION</div>',
    unsafe_allow_html=True,
)
render_concentration(weights)

st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">SECTOR BREAKDOWN</div>',
    unsafe_allow_html=True,
)
render_sector_breakdown(holdings_meta)

st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">QUALITY SCREEN</div>',
    unsafe_allow_html=True,
)
render_quality_screen(bundles, weights)


# ============================================================
# Correlation · Risk decomposition (need price history)
# ============================================================
with st.spinner("Pulling 3y price history for risk analytics…"):
    returns = _portfolio_returns(tickers_tuple, period="3y")

if not returns.empty and len(returns) >= 60:
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">CORRELATION</div>',
        unsafe_allow_html=True,
    )
    render_correlation_heatmap(returns)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'RISK DECOMPOSITION</div>',
        unsafe_allow_html=True,
    )
    render_risk_decomposition(returns, weights)
else:
    st.info(
        "Correlation + risk decomposition need ≥60 days of overlapping "
        "price history. Skipped (insufficient data for current holdings)."
    )


# ============================================================
# Stress tests (5 scenarios — replaces old single-slider stress)
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">STRESS TESTS</div>',
    unsafe_allow_html=True,
)
render_stress_tests(holdings_meta, current_prices)


# ============================================================
# Markowitz frontier — educational, behind expander
# ============================================================
with st.expander("Markowitz frontier (educational)"):
    if not returns.empty and len(returns) >= 60:
        render_markowitz_frontier(returns, weights)
    else:
        st.info("Markowitz needs ≥60 days of returns history.")


# ============================================================
# Historical VaR (optional, expander)
# ============================================================
with st.expander("📊 Value at Risk · 1-day · 95%"):
    try:
        import yfinance as yf
        from portfolio.var_calculator import value_at_risk, conditional_var
    except Exception as exc:
        st.caption(f"VaR unavailable: {exc}")
    else:
        tickers = [h["ticker"] for h in holdings]
        weights = pd.Series({h["ticker"]: h["value"] / total_value
                             for h in holdings})
        try:
            with st.spinner("Pulling 2y history for VaR…"):
                prices = yf.download(tickers, period="2y",
                                     progress=False, auto_adjust=True)
                prices = prices["Close"] if isinstance(prices.columns, pd.MultiIndex) else prices
                if isinstance(prices, pd.Series):
                    prices = prices.to_frame(name=tickers[0])
                returns = prices.pct_change().dropna(how="all")
                portfolio_returns = (returns * weights).sum(axis=1).dropna()
            var_pct = value_at_risk(portfolio_returns, confidence=0.95,
                                     method="historical", signed=True)
            cvar_pct = conditional_var(portfolio_returns, confidence=0.95,
                                        signed=True)
            var_dollar = float(var_pct) * total_value
            cvar_dollar = float(cvar_pct) * total_value
            v1, v2 = st.columns(2)
            v1.metric("VaR (1d, 95%)",
                      f"${abs(var_dollar):,.0f}",
                      f"{var_pct*100:+.2f}% of portfolio")
            v2.metric("CVaR (Expected Shortfall)",
                      f"${abs(cvar_dollar):,.0f}",
                      f"{cvar_pct*100:+.2f}% avg in tail")
            st.caption(
                f"Historical method · {len(portfolio_returns)} obs of "
                "weighted-portfolio returns · 95% confidence."
            )
        except Exception as exc:
            st.caption(f"VaR computation failed: {exc}")
