"""
Portfolio optimizer — landing state with templates + analysis state with
tabs (Weights · Frontier · Backtest · Compare · Correlation · Monte Carlo).

Live data via yfinance (cached for 10 minutes). Supports six objectives:
Max Sharpe · Min Vol · Risk Parity · HRP · Equal Weight · Black-Litterman.
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

from core.constants import PORTFOLIO_DEFAULTS
from data.market_data import get_price_panel, get_spx_history
from data.watchlist_db import list_watchlist
from portfolio.backtest import walk_forward
from portfolio.optimizer import (
    OptimizationResult,
    max_sharpe, min_vol, risk_parity, equal_weight, efficient_frontier,
    hrp, black_litterman,
)
from portfolio.shrinkage import ledoit_wolf
from portfolio.var_calculator import compute_risk_metrics, RiskMetrics
from ui.charts.efficient_frontier import build_frontier_figure
from ui.charts.drawdown_chart import build_backtest_figure
from ui.components.correlation_heatmap import render_correlation_heatmap
from ui.components.portfolio_landing import render_portfolio_landing, TEMPLATES
from ui.components.portfolio_monte_carlo import render_portfolio_monte_carlo
from ui.components.risk_contribution import render_risk_contribution
from ui.components.sector_breakdown import render_sector_breakdown
from ui.components.strategy_comparison import render_strategy_comparison


# ============================================================
# Helpers
# ============================================================
_OBJECTIVE_KEYS: dict[str, str] = {
    "Max Sharpe":       "max_sharpe",
    "Min Vol":          "min_vol",
    "Risk Parity":      "risk_parity",
    "HRP":              "hrp",
    "Equal Weight":     "equal_weight",
    "Black-Litterman":  "black_litterman",
}


def _parse_tickers(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in raw.replace(";", ",").split(","):
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _gold_bar_html(pct: float, *, max_pct: float = 100.0) -> str:
    """Inline single-line HTML for a gold weight bar (replaces the
    red ProgressColumn that hard-codes its colour)."""
    fill = max(0.0, min(100.0, pct / max_pct * 100.0))
    return (
        '<div style="background:var(--surface-raised); height:8px; '
        'border-radius:4px; overflow:hidden;">'
        f'<div style="background:rgba(201,169,97,0.85); width:{fill}%; '
        f'height:100%;"></div></div>'
    )


def _render_weights_table(weights: pd.Series) -> None:
    """Custom HTML weights table — gold bars + tabular numbers."""
    df = (
        weights[weights > 1e-4]
        .sort_values(ascending=False)
        .rename("weight")
        .reset_index()
        .rename(columns={"index": "Ticker"})
    )
    if df.empty:
        st.info("No active positions in this allocation.")
        return
    df["Weight %"] = df["weight"] * 100.0
    max_w = float(df["Weight %"].max()) or 1.0

    rows = []
    for _, r in df.iterrows():
        rows.append(
            '<tr>'
            f'<td style="padding:8px 12px; color:var(--text-primary); '
            f'font-weight:500; font-size:13px;">{r["Ticker"]}</td>'
            f'<td style="padding:8px 12px; text-align:right; '
            f'color:var(--text-primary); font-variant-numeric:tabular-nums; '
            f'font-size:13px;">{r["Weight %"]:.2f}%</td>'
            f'<td style="padding:8px 12px; width:55%;">'
            + _gold_bar_html(r["Weight %"], max_pct=max_w)
            + '</td>'
            '</tr>'
        )
    head = (
        '<thead><tr style="background:#1A2033;">'
        '<th style="padding:10px 12px; text-align:left; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Ticker</th>'
        '<th style="padding:10px 12px; text-align:right; font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; color:#9CA3AF;">'
        'Weight</th>'
        '<th></th>'
        '</tr></thead>'
    )
    table_html = (
        '<div style="background:#131826; border:1px solid #1F2937; '
        'border-radius:8px; overflow:auto;">'
        '<table style="width:100%; border-collapse:collapse;">'
        + head + '<tbody>' + "".join(rows) + '</tbody></table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ============================================================
# Sidebar — risk controls (slimmed down — most config moved to the body)
# ============================================================
def _control_sidebar() -> dict:
    with st.sidebar:
        st.markdown(
            '<div style="color:var(--accent); font-size:11px; font-weight:500; '
            'letter-spacing:1px; text-transform:uppercase; padding:4px 0 8px 0; '
            'border-bottom:1px solid var(--border); margin-bottom:12px;">'
            'Risk controls</div>',
            unsafe_allow_html=True,
        )
        risk_free = st.number_input(
            "Risk-free rate", value=PORTFOLIO_DEFAULTS["risk_free_rate"],
            step=0.005, format="%.3f",
            help="Annualized — typically the 10Y Treasury yield.",
        )
        max_pos = st.number_input(
            "Max position", value=PORTFOLIO_DEFAULTS["max_position_size"] * 100,
            min_value=5.0, max_value=100.0, step=5.0, format="%.1f",
            help="Per-ticker cap. 100% means no upper bound.",
        ) / 100.0
        min_pos = st.number_input(
            "Min position", value=0.0,
            min_value=0.0, max_value=20.0, step=1.0, format="%.1f",
            help="Per-ticker floor. 0 lets the optimizer drop names.",
        ) / 100.0

        st.markdown(
            '<div style="color:var(--accent); font-size:11px; font-weight:500; '
            'letter-spacing:1px; text-transform:uppercase; padding:4px 0 8px 0; '
            'border-bottom:1px solid var(--border); margin:18px 0 12px 0;">'
            'Backtest</div>',
            unsafe_allow_html=True,
        )
        run_bt = st.checkbox("Run walk-forward backtest", value=True)
        train_pct = st.slider(
            "Training share", min_value=0.50, max_value=0.90,
            value=PORTFOLIO_DEFAULTS["backtest_train_pct"], step=0.05,
        )

    return {
        "risk_free": risk_free, "max_position": max_pos,
        "min_position": min_pos,
        "run_backtest": run_bt, "train_pct": train_pct,
    }


# ============================================================
# Page entry
# ============================================================
controls = _control_sidebar()


# ---- Pre-fill state from a clicked template / watchlist ----
prefill = st.session_state.get("portfolio_prefill", {})
default_tickers = prefill.get("tickers", "AAPL,MSFT,GOOGL,NVDA,AMZN,JPM,XOM,JNJ,KO,WMT")
default_objective = prefill.get("objective", "Max Sharpe")
default_years = prefill.get("years", 5)


# ============================================================
# Toolbar (always visible) — inputs + Optimize
# ============================================================
st.markdown(
    '<div class="eq-section-label">PORTFOLIO OPTIMIZER</div>',
    unsafe_allow_html=True,
)

ic1, ic2, ic3, ic4 = st.columns([3, 1, 1.4, 1])
with ic1:
    tickers_raw = st.text_input(
        "Tickers", value=default_tickers,
        label_visibility="collapsed",
        placeholder="TICKERS (comma-separated)",
    )
with ic2:
    years = st.number_input(
        "Years", min_value=1, max_value=10, value=int(default_years), step=1,
        label_visibility="collapsed",
    )
with ic3:
    objective = st.selectbox(
        "Objective",
        list(_OBJECTIVE_KEYS.keys()),
        index=list(_OBJECTIVE_KEYS.keys()).index(default_objective)
              if default_objective in _OBJECTIVE_KEYS else 0,
        label_visibility="collapsed",
    )
with ic4:
    optimize_btn = st.button(
        "Optimize", type="primary", use_container_width=True,
    )


# ============================================================
# LANDING STATE — show only when nothing has been optimized yet
# ============================================================
if optimize_btn:
    st.session_state["po_loaded"] = True
    st.session_state.pop("portfolio_prefill", None)        # consumed

if not st.session_state.get("po_loaded"):
    chosen = render_portfolio_landing(
        watchlist_size=len(list_watchlist()),
    )
    if chosen:
        # Map template into the toolbar inputs and trigger an optimize on next run
        if chosen.get("from_watchlist"):
            wl = list_watchlist()
            tickers_str = ",".join(wl) if wl else default_tickers
        else:
            tickers_str = ",".join(chosen["tickers"])
        st.session_state["portfolio_prefill"] = {
            "tickers":   tickers_str,
            "objective": chosen.get("objective", "Max Sharpe"),
            "years":     5,
        }
        st.session_state["po_loaded"] = True
        st.rerun()
    st.stop()


# ============================================================
# ANALYSIS STATE — fetch data + run optimizer
# ============================================================
tickers = _parse_tickers(tickers_raw)
if len(tickers) < 2:
    st.error("Provide at least 2 tickers separated by commas.")
    st.stop()

period = f"{int(years)}y"
with st.spinner(f"Fetching {len(tickers)} tickers · {period} of daily prices…"):
    prices = get_price_panel(tuple(tickers), period=period, interval="1d")

if prices is None or prices.empty:
    st.error("yfinance returned no data — check the tickers or shorten the window.")
    st.stop()

missing = [t for t in tickers if t not in prices.columns]
if missing:
    st.warning(f"Dropped (no data): {', '.join(missing)}")
prices = prices[[t for t in tickers if t in prices.columns]].dropna(how="any")

if prices.shape[0] < 60 or prices.shape[1] < 2:
    st.error("Not enough overlapping observations after cleaning.")
    st.stop()

returns = prices.pct_change().dropna(how="any")


# ---- Run the requested objective ----
obj_kwargs = {
    "risk_free":    controls["risk_free"],
    "max_position": controls["max_position"],
    "min_position": controls["min_position"],
}
try:
    if objective == "Max Sharpe":
        res = max_sharpe(returns, **obj_kwargs)
    elif objective == "Min Vol":
        res = min_vol(returns, **obj_kwargs)
    elif objective == "Risk Parity":
        res = risk_parity(returns,
                          risk_free=controls["risk_free"],
                          max_position=controls["max_position"],
                          min_position=1e-6)
    elif objective == "HRP":
        res = hrp(returns, risk_free=controls["risk_free"])
    elif objective == "Equal Weight":
        res = equal_weight(returns, risk_free=controls["risk_free"])
    elif objective == "Black-Litterman":
        # Equilibrium = equal-weight prior (no views by default; UI for
        # views can land in a follow-up commit).
        n = returns.shape[1]
        mc_proxy = pd.Series(1.0 / n, index=returns.columns)
        res = black_litterman(
            returns, market_weights=mc_proxy,
            views=None,
            max_position=controls["max_position"],
            min_position=controls["min_position"],
            risk_free=controls["risk_free"],
        )
    else:
        st.error(f"Unknown objective: {objective}")
        st.stop()
except Exception as exc:
    st.error(f"Optimization failed: {exc}")
    st.stop()

if not res.converged and objective != "Equal Weight":
    st.warning(f"Optimizer did not fully converge: {res.message}")


# ---- Header metrics: native st.metric (fixes the </div> leak) ----
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)
m1.metric("EXPECTED RETURN", f"{res.expected_return * 100:.2f}%")
m2.metric("VOLATILITY",      f"{res.volatility * 100:.2f}%")
m3.metric("SHARPE",          f"{res.sharpe:.3f}")
m4.metric("ASSETS",
          f"{int((res.weights > 1e-3).sum())} / {len(res.weights)}")


# ============================================================
# Tabs — Weights · Frontier · Backtest · Compare · Correlation · MC
# ============================================================
st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
tab_w, tab_f, tab_b, tab_c, tab_corr, tab_mc = st.tabs([
    "Weights", "Frontier", "Backtest", "Compare", "Correlation", "Monte Carlo",
])


# ---- WEIGHTS ----
with tab_w:
    st.markdown(
        '<div class="eq-section-label">OPTIMAL WEIGHTS</div>',
        unsafe_allow_html=True,
    )
    _render_weights_table(res.weights)

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">SECTOR BREAKDOWN</div>',
        unsafe_allow_html=True,
    )
    render_sector_breakdown(res.weights)

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">RISK CONTRIBUTION</div>',
        unsafe_allow_html=True,
    )
    cov_full = ledoit_wolf(returns).covariance
    render_risk_contribution(res.weights, cov_full)
    st.caption(
        "Risk contribution can diverge sharply from capital weight — a "
        "high-volatility name can drive most of the portfolio variance "
        "even when its dollar exposure looks modest."
    )


# ---- FRONTIER ----
with tab_f:
    st.markdown(
        '<div class="eq-section-label">EFFICIENT FRONTIER</div>',
        unsafe_allow_html=True,
    )
    with st.spinner("Sweeping the efficient frontier…"):
        try:
            ef = efficient_frontier(
                returns, n_points=25,
                max_position=controls["max_position"],
                min_position=controls["min_position"],
            )
        except Exception as exc:
            ef = pd.DataFrame()
            st.warning(f"Frontier sweep failed: {exc}")

    cov_arr = ledoit_wolf(returns).covariance.values
    asset_pts = pd.DataFrame({
        "return":     returns.mean() * 252,
        "volatility": np.sqrt(np.diag(cov_arr)),
    }, index=returns.columns)

    selected = ({
        "return":     res.expected_return,
        "volatility": res.volatility,
        "label":      objective,
    } if res.volatility > 0 else None)

    st.plotly_chart(
        build_frontier_figure(ef, assets=asset_pts, selected=selected),
        use_container_width=True, config={"displayModeBar": False},
    )


# ---- BACKTEST ----
with tab_b:
    if not controls["run_backtest"]:
        st.info("Backtest is disabled in the sidebar.")
    else:
        st.markdown(
            '<div class="eq-section-label">WALK-FORWARD BACKTEST · vs S&P 500</div>',
            unsafe_allow_html=True,
        )
        bench_hist = get_spx_history(period=period)
        bench_close = (bench_hist["Close"].dropna()
                       if "Close" in bench_hist.columns else None)

        try:
            obj_key = _OBJECTIVE_KEYS[objective]
            bt_kwargs = obj_kwargs.copy()
            if obj_key in {"hrp", "equal_weight"}:
                bt_kwargs = {"risk_free": controls["risk_free"]}
            elif obj_key == "black_litterman":
                # Strip kwargs the BL signature won't accept on the
                # backtest re-fits (market_weights is passed positionally
                # at run time, which walk_forward doesn't know about).
                bt_kwargs = {"risk_free": controls["risk_free"]}
                obj_key = "max_sharpe"          # fall back for backtest
            bt = walk_forward(
                prices=prices,
                objective=obj_key,
                train_pct=controls["train_pct"],
                benchmark_prices=bench_close,
                optimizer_kwargs=bt_kwargs,
            )
        except Exception as exc:
            st.warning(f"Backtest failed: {exc}")
        else:
            t1, t2, t3 = st.columns(3)
            t1.metric("TRAIN WINDOW",
                      f"{bt.train_start.date()} → {bt.train_end.date()}")
            t2.metric("OOS WINDOW",
                      f"{bt.oos_start.date()} → {bt.oos_end.date()}")
            final_port = float(bt.cumulative["portfolio"].iloc[-1])
            t3.metric("OOS WEALTH (×)", f"{final_port:,.3f}")

            st.plotly_chart(
                build_backtest_figure(
                    bt.portfolio_returns,
                    benchmark_returns=bt.benchmark_returns,
                    portfolio_label=objective,
                    benchmark_label="S&P 500",
                ),
                use_container_width=True, config={"displayModeBar": False},
            )

            oos_metrics = compute_risk_metrics(
                bt.portfolio_returns, risk_free_annual=controls["risk_free"],
            )
            oos_summary = pd.DataFrame([
                {"Metric": "OOS annual return", "Value": f"{oos_metrics.annual_return:.2%}"},
                {"Metric": "OOS volatility",    "Value": f"{oos_metrics.annual_volatility:.2%}"},
                {"Metric": "OOS Sharpe",        "Value": f"{oos_metrics.sharpe:.3f}"},
                {"Metric": "OOS max DD",        "Value": f"{oos_metrics.max_drawdown:.2%}"},
            ])
            if bt.benchmark_returns is not None and not bt.benchmark_returns.empty:
                bm = compute_risk_metrics(
                    bt.benchmark_returns, risk_free_annual=controls["risk_free"],
                )
                oos_summary["Benchmark"] = [
                    f"{bm.annual_return:.2%}",
                    f"{bm.annual_volatility:.2%}",
                    f"{bm.sharpe:.3f}",
                    f"{bm.max_drawdown:.2%}",
                ]
            st.dataframe(oos_summary, hide_index=True, use_container_width=True)


# ---- COMPARE — runs every objective on the same data ----
with tab_c:
    st.markdown(
        '<div class="eq-section-label">STRATEGY COMPARISON</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Same return panel, every objective. Best metric per column "
        "is tinted green so trade-offs are easy to spot."
    )
    render_strategy_comparison(
        returns,
        risk_free=controls["risk_free"],
        max_position=controls["max_position"],
        min_position=controls["min_position"],
    )


# ---- CORRELATION ----
with tab_corr:
    st.markdown(
        '<div class="eq-section-label">CORRELATION MATRIX · DAILY RETURNS</div>',
        unsafe_allow_html=True,
    )
    render_correlation_heatmap(returns, height=420)


# ---- MONTE CARLO PROJECTION ----
with tab_mc:
    st.markdown(
        '<div class="eq-section-label">MONTE CARLO PROJECTION · 10-YEAR HORIZON</div>',
        unsafe_allow_html=True,
    )
    port_returns = (returns * res.weights).sum(axis=1)
    render_portfolio_monte_carlo(
        port_returns,
        years=10, n_simulations=5_000, initial_wealth=10_000.0,
    )


# ============================================================
# Reset back to landing
# ============================================================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
back_l, _, _ = st.columns([1, 4, 1])
with back_l:
    if st.button("← Back to templates", key="po_back",
                 type="secondary", use_container_width=True):
        st.session_state.pop("po_loaded", None)
        st.session_state.pop("portfolio_prefill", None)
        st.rerun()


st.caption(
    "Data via yfinance (cached 10 min). Stress testing and rebalancing "
    "analysis are deferred to the next pass — they need historical "
    "scenario data and a current-holdings input flow that aren't wired yet."
)
