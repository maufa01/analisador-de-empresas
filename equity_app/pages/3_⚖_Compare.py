"""
Compare — side-by-side analysis of 2-3 tickers (P11.B1).

One page, dense table, projected FCF chart. Every ticker reuses the
cached :func:`load_bundle` so subsequent visits hit the cache instead
of refetching.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.parallel_loader import load_bundle
from analysis.ratios import calculate_ratios


# ============================================================
# Direct yfinance fallback — used when the cached bundle is partial
# (FMP rate-limited / Finnhub down / yfinance scrape-blocked at the
# time the bundle was hydrated). Bypasses the bundle cache so we
# get fresh metadata without burning an FMP call.
#
# Returns a dict so the caller can pull `price`, `market_cap`,
# `sector`, `name` independently — each field falls back to None
# if yfinance doesn't have it (rare for major US tickers).
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def _yf_meta(ticker: str) -> dict:
    out: dict = {"price": None, "market_cap": None,
                  "sector": None, "name": None}
    try:
        import yfinance as yf
    except Exception:
        return out

    try:
        t = yf.Ticker(ticker)
    except Exception:
        return out

    # ---- fast_info (cheap, no scrape) — price + market_cap ----
    try:
        fi = t.fast_info
        # price
        for key in ("last_price", "lastPrice",
                    "regular_market_price", "regularMarketPrice"):
            try:
                v = fi[key] if key in fi else getattr(fi, key, None)
            except (KeyError, TypeError):
                v = getattr(fi, key, None)
            if v is not None:
                try:
                    p = float(v)
                    if p > 0:
                        out["price"] = p
                        break
                except (TypeError, ValueError):
                    continue
        # market_cap
        for key in ("market_cap", "marketCap"):
            try:
                v = fi[key] if key in fi else getattr(fi, key, None)
            except (KeyError, TypeError):
                v = getattr(fi, key, None)
            if v is not None:
                try:
                    mc = float(v)
                    if mc > 0:
                        out["market_cap"] = mc
                        break
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    # ---- .info (slower, scrape — only call if we need sector/name) ----
    if out["sector"] is None or out["name"] is None:
        try:
            full = t.info or {}
            out["sector"] = (out["sector"] or full.get("sector")
                              or full.get("sectorDisp"))
            out["name"] = (out["name"]
                            or full.get("longName")
                            or full.get("shortName"))
            # market_cap fallback from .info if fast_info didn't have it
            if out["market_cap"] is None and full.get("marketCap"):
                try:
                    out["market_cap"] = float(full["marketCap"])
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass
    return out


# ============================================================
# Header
# ============================================================
st.markdown(
    '<div class="eq-section-label">⚖ COMPARE</div>',
    unsafe_allow_html=True,
)
st.caption("Side-by-side analysis of 2-3 tickers. Reuses the cached bundle.")


# ============================================================
# Ticker inputs
# ============================================================
c1, c2, c3 = st.columns(3)
t1 = c1.text_input("Ticker 1", "AAPL").upper().strip()
t2 = c2.text_input("Ticker 2", "MSFT").upper().strip()
t3 = c3.text_input("Ticker 3 (optional)", "").upper().strip()

tickers = [t for t in (t1, t2, t3) if t]
if len(tickers) < 2:
    st.info("Enter at least 2 tickers to compare.")
    st.stop()


# ============================================================
# Bundle hydration (cached, parallel)
# ============================================================
with st.spinner(f"Loading {len(tickers)} tickers…"):
    bundles = {t: load_bundle(t) for t in tickers}


# ============================================================
# Metric extraction per ticker
# ============================================================
def _money_compact(v: Optional[float]) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "—"
    av = abs(v)
    if av >= 1e12:
        return f"${av/1e12:.2f}T"
    if av >= 1e9:
        return f"${av/1e9:.1f}B"
    if av >= 1e6:
        return f"${av/1e6:.1f}M"
    return f"${av:,.0f}"


def _pct(v) -> str:
    if v is None or not isinstance(v, (int, float)) or pd.isna(v):
        return "—"
    return f"{v:.1f}%"


def _ratio(v) -> str:
    if v is None or not isinstance(v, (int, float)) or pd.isna(v):
        return "—"
    return f"{v:.2f}"


def _last(ratios: pd.DataFrame, col: str):
    if ratios is None or ratios.empty or col not in ratios.columns:
        return None
    s = ratios[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _try_implied_growth(bundle, current_price, shares) -> Optional[float]:
    """Best-effort reverse DCF — fails silently for banks/REITs."""
    if not (current_price and shares and shares > 0):
        return None
    try:
        from valuation.reverse_dcf import run_reverse_dcf
        # Implied per-share growth = run_reverse_dcf with target = current price
        # The function expects target_price as TOTAL equity / share;
        # since shares × per-share = mcap, target_price as a per-share works.
        res = run_reverse_dcf(
            income=bundle.income, balance=bundle.balance, cash=bundle.cash,
            target_price=float(current_price),
            wacc=0.10,            # rough default for cross-ticker comparison
        )
        return res.implied_growth if res and res.implied_growth is not None else None
    except Exception:
        return None


def _extract_metrics(ticker: str, bundle) -> dict:
    if bundle.income.empty:
        return {"Ticker": ticker, "Status": "no_data"}
    info = bundle.info or {}
    ratios = calculate_ratios(bundle.income, bundle.balance, bundle.cash)
    price = bundle.quote.get("price") if bundle.quote else None
    market_cap = info.get("marketCap") or info.get("market_cap")
    sector = info.get("sector")
    name = info.get("name") or info.get("longName") or info.get("shortName")

    # If the cached bundle is thin (FMP rate-limited / yfinance scrape
    # blocked at the time), fall back to a direct yfinance fast_info
    # lookup. This is cheap, cached 5min, and doesn't burn an FMP call.
    if (price is None or price <= 0) or not market_cap or not sector or not name:
        yf_meta = _yf_meta(ticker)
        if price is None or price <= 0:
            price = yf_meta.get("price")
        if not market_cap:
            market_cap = yf_meta.get("market_cap")
        if not sector:
            sector = yf_meta.get("sector")
        if not name:
            name = yf_meta.get("name")
    if not name:
        name = ticker

    shares = (info.get("sharesOutstanding")
              or info.get("shares_outstanding"))
    implied = _try_implied_growth(bundle, price, shares)

    return {
        "Ticker":      ticker,
        "Name":        str(name)[:30],
        "Sector":      sector or "—",
        "Price":       f"${price:.2f}" if price else "—",
        "Mkt Cap":     _money_compact(market_cap),
        "Gross Margin %":     _pct(_last(ratios, "Gross Margin %")),
        "Op Margin %":        _pct(_last(ratios, "Operating Margin %")),
        "Net Margin %":       _pct(_last(ratios, "Net Margin %")),
        "FCF Margin %":       _pct(_last(ratios, "FCF Margin %")),
        "ROIC %":      _pct(_last(ratios, "ROIC %")),
        "ROE %":       _pct(_last(ratios, "ROE %")),
        "Debt/Equity": _ratio(_last(ratios, "Debt/Equity")),
        "Implied growth": _pct(implied * 100.0 if implied is not None else None),
    }


rows = [_extract_metrics(t, b) for t, b in bundles.items()]
df = pd.DataFrame(rows)

# Render transposed — metrics as rows, tickers as columns. More natural
# for visual comparison than tickers-as-rows.
st.markdown(
    '<div class="eq-section-label" style="margin-top:14px;">'
    'SIDE-BY-SIDE</div>',
    unsafe_allow_html=True,
)
display = df.set_index("Ticker").T
st.dataframe(display, use_container_width=True)


# ============================================================
# Historical price loader for multiples spread (cached 6h)
# ============================================================
@st.cache_data(ttl=21_600, show_spinner=False)
def _hist_prices(_tickers: tuple[str, ...]) -> dict:
    from data.market_data import _yfinance
    yf = _yfinance()
    if yf is None:
        return {}
    out: dict[str, pd.DataFrame] = {}
    for t in _tickers:
        try:
            hist = yf.Ticker(t).history(period="5y")[["Close"]]
            if not hist.empty:
                out[t] = hist
        except Exception:
            continue
    return out


prices_hist = _hist_prices(tuple(tickers))
prices_now = {t: bundles[t].quote.get("price") for t in tickers}

# Per-ticker WACC: default 10% across the board for cross-ticker
# comparability. Computing a real WACC per ticker would need a beta
# regression + cost-of-debt resolution and the extra precision rarely
# changes the reverse-DCF conclusion at this resolution.
waccs = {t: 0.10 for t in tickers}


# ============================================================
# Trajectory overlays
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'TRAJECTORY</div>',
    unsafe_allow_html=True,
)
from ui.components.compare_trajectories import render_compare_trajectories
render_compare_trajectories(bundles)


# ============================================================
# Quality scorecard
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'QUALITY SCORECARD</div>',
    unsafe_allow_html=True,
)
from ui.components.compare_quality_scorecard import render_quality_scorecard
market_caps = {t: bundles[t].market_cap for t in tickers}
render_quality_scorecard(bundles, market_caps)


# ============================================================
# Capital allocation (cumulative 5y)
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'CAPITAL ALLOCATION · CUMULATIVE 5Y</div>',
    unsafe_allow_html=True,
)
from ui.components.compare_capital_allocation import render_compare_capital_allocation
render_compare_capital_allocation(bundles)


# ============================================================
# Reverse DCF spread cards
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'REVERSE DCF · IMPLIED GROWTH</div>',
    unsafe_allow_html=True,
)
from ui.components.compare_reverse_dcf_spread import render_reverse_dcf_spread
render_reverse_dcf_spread(bundles, prices_now, waccs)


# ============================================================
# Forecasted FCF chart
# ============================================================
st.markdown(
    '<div class="eq-section-label" style="margin-top:18px;">'
    'PROJECTED FREE CASH FLOW · 5-YEAR</div>',
    unsafe_allow_html=True,
)

_LINE_COLORS = ["#3B82F6", "#C9A961", "#10B981"]

fig = go.Figure()
for i, (ticker, bundle) in enumerate(bundles.items()):
    if bundle.income.empty:
        continue
    try:
        from analysis.financial_forecast import (
            _default_inputs_from_history, project_financials,
        )
        info = bundle.info or {}
        shares = (info.get("sharesOutstanding")
                  or info.get("shares_outstanding"))
        inp = _default_inputs_from_history(bundle.income, bundle.balance,
                                            bundle.cash, years=5)
        result = project_financials(
            bundle.income, bundle.balance, bundle.cash,
            inputs=inp, years=5, shares_outstanding=shares,
        )
        if result.fcff_per_year is None or result.fcff_per_year.empty:
            continue
        years_axis = [d.year if isinstance(d, pd.Timestamp) else int(d)
                      for d in result.fcff_per_year.index]
        fig.add_trace(go.Scatter(
            x=years_axis,
            y=result.fcff_per_year.values / 1e9,
            name=ticker, mode="lines+markers",
            line=dict(color=_LINE_COLORS[i % len(_LINE_COLORS)], width=2),
            marker=dict(size=8),
        ))
    except Exception:
        continue

fig.update_layout(
    plot_bgcolor="#131826", paper_bgcolor="#131826",
    font=dict(color="#9CA3AF", family="Inter, sans-serif", size=11),
    height=380,
    margin=dict(l=0, r=0, t=20, b=0),
    yaxis=dict(title="Annual FCF ($B)", gridcolor="#1F2937", color="#6B7280"),
    xaxis=dict(gridcolor="#1F2937", color="#6B7280"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
)
st.plotly_chart(fig, use_container_width=True,
                config={"displayModeBar": False})

st.caption(
    "Forecast inputs default to each ticker's own historical CAGR + "
    "3y-avg margins. WACC for the implied-growth column is fixed at "
    "10% across all tickers for apples-to-apples comparison."
)


# ============================================================
# Multiples spread (pair-trade z-score) — only when N == 2
# ============================================================
if len(tickers) == 2:
    st.markdown(
        '<div class="eq-section-label" style="margin-top:18px;">'
        'MULTIPLES SPREAD · PAIR-TRADE Z-SCORE</div>',
        unsafe_allow_html=True,
    )
    from ui.components.compare_multiples_spread import render_multiples_spread
    render_multiples_spread(bundles, prices_hist)
