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
# Holdings input — 3 modes (Preset / Custom / Raw text)
# ============================================================
from ui.components.portfolio_input import render_portfolio_input

holdings_input = render_portfolio_input()

if not holdings_input or not holdings_input.strip():
    st.info(
        "Choose a Preset, build a Custom portfolio, or paste Raw text "
        "to begin."
    )
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

# Expose total $ to session so Compare tab "Use this template" can
# rebuild new-weight holdings against the real portfolio value.
st.session_state["portfolio_total_value"] = total_value


# ============================================================
# Load bundles + returns once (shared across tabs)
# ============================================================
tickers_tuple = tuple(sorted(h["ticker"] for h in holdings))
weights = {h["ticker"]: h["value"] / total_value for h in holdings}
current_prices = {h["ticker"]: h["price"] for h in holdings}

with st.spinner("Loading sector + fundamentals…"):
    bundles = _bundles_for(tickers_tuple)
with st.spinner("Pulling 3y price history…"):
    returns = _portfolio_returns(tickers_tuple, period="3y")

# holdings-meta used by sector + stress components
holdings_meta = {
    h["ticker"]: {
        "weight": h["value"] / total_value,
        "sector": getattr(bundles.get(h["ticker"]), "sector", None),
        "value":  h["value"],
    }
    for h in holdings
}


# ============================================================
# Headline KPI cards
# ============================================================
from ui.components.portfolio_markowitz import compute_strategy_metrics

has_returns = (not returns.empty) and (len(returns) >= 60)
if has_returns:
    _metrics = compute_strategy_metrics(returns, weights)
    exp_return = _metrics.get("expected_return")
    vol = _metrics.get("volatility")
    sharpe = _metrics.get("sharpe")
else:
    exp_return = vol = sharpe = None

k1, k2, k3, k4 = st.columns(4)
k1.metric("TOTAL VALUE", f"${total_value:,.0f}",
           f"${total_pl:+,.0f} P/L" if total_pl else None)
k2.metric("EXPECTED RETURN",
           f"{exp_return:.1%}" if exp_return is not None else "—",
           help="Annualized from trailing 3y daily returns × current weights")
k3.metric("VOLATILITY",
           f"{vol:.1%}" if vol is not None else "—",
           help="Annualized portfolio σ from cov matrix")
k4.metric("SHARPE",
           f"{sharpe:.2f}" if sharpe is not None else "—",
           help="Expected return / volatility (rf=0)")
st.caption(
    "Trailing 3y daily returns. Sharpe assumes zero risk-free rate "
    "for comparability across regimes."
)


# ============================================================
# Tabs
# ============================================================
tab_comp, tab_risk, tab_quality, tab_stress, tab_frontier, tab_compare = st.tabs([
    "Composition", "Risk", "Quality", "Stress",
    "Frontier", "Compare strategies",
])

with tab_comp:
    st.markdown(
        '<div class="eq-section-label">HOLDINGS</div>',
        unsafe_allow_html=True,
    )
    display_df = df[["ticker", "shares", "cost", "price",
                     "value", "weight_%", "pl_$"]].copy()
    display_df.columns = ["Ticker", "Shares", "Cost", "Price",
                           "Value", "Weight %", "P/L $"]
    st.dataframe(display_df.round(2), hide_index=True,
                  use_container_width=True)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'CONCENTRATION</div>',
        unsafe_allow_html=True,
    )
    render_concentration(weights)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'SECTOR BREAKDOWN</div>',
        unsafe_allow_html=True,
    )
    render_sector_breakdown(holdings_meta)

with tab_risk:
    if has_returns:
        st.markdown(
            '<div class="eq-section-label">CORRELATION</div>',
            unsafe_allow_html=True,
        )
        render_correlation_heatmap(returns)

        st.markdown(
            '<div class="eq-section-label" style="margin-top:18px;">'
            'RISK DECOMPOSITION</div>',
            unsafe_allow_html=True,
        )
        render_risk_decomposition(returns, weights)

        # ---- Historical Value at Risk · 1-day · 95% ----
        st.markdown(
            '<div class="eq-section-label" style="margin-top:18px;">'
            'VALUE AT RISK · 1-DAY · 95%</div>',
            unsafe_allow_html=True,
        )
        try:
            from portfolio.var_calculator import value_at_risk, conditional_var
        except Exception as exc:
            st.caption(f"VaR unavailable: {exc}")
        else:
            # Reuse the already-fetched 3y returns; build weighted portfolio
            # return series in-place.
            try:
                w_series = pd.Series(weights).reindex(returns.columns).fillna(0.0)
                portfolio_returns = (returns * w_series).sum(axis=1).dropna()
                if len(portfolio_returns) < 60:
                    st.caption("Not enough observations for VaR (need ≥60).")
                else:
                    var_pct = value_at_risk(portfolio_returns,
                                             confidence=0.95,
                                             method="historical", signed=True)
                    cvar_pct = conditional_var(portfolio_returns,
                                                confidence=0.95, signed=True)
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
                        f"Historical method · {len(portfolio_returns)} obs "
                        "of weighted-portfolio returns · 95% confidence."
                    )
            except Exception as exc:
                st.caption(f"VaR computation failed: {exc}")
    else:
        st.info("Risk analytics need ≥60 days of overlapping price history.")

with tab_quality:
    render_quality_screen(bundles, weights)

with tab_stress:
    render_stress_tests(holdings_meta, current_prices)

with tab_frontier:
    if has_returns:
        render_markowitz_frontier(returns, weights)
    else:
        st.info("Markowitz frontier needs ≥60 days of returns history.")

with tab_compare:
    from ui.components.portfolio_strategy_compare import render_strategy_compare
    if has_returns:
        render_strategy_compare(returns, weights, current_prices)
    else:
        st.info("Strategy comparison requires ≥60 days of price history.")


