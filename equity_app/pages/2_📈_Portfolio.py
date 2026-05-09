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
# Stress slider
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'MARKET-SHOCK STRESS</div>',
    unsafe_allow_html=True,
)
shock = st.slider(
    "Market shock", min_value=-50, max_value=30, value=-30, step=5,
    format="%+d%%",
    help="Apply a flat shock across all holdings — first-order estimate "
         "of dollar exposure.",
)
shock_pct = shock / 100.0
new_total = total_value * (1.0 + shock_pct)
delta = new_total - total_value
sc1, sc2 = st.columns(2)
sc1.metric("After shock", f"${new_total:,.0f}", f"{shock:+d}%")
sc2.metric("Dollar change", f"${delta:+,.0f}")


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
        weights = pd.Series({h["ticker"]: h["weight_%"] / 100.0
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
