"""
Portfolio optimizer — Markowitz mean-variance with Ledoit-Wolf shrinkage,
risk-parity (ERC), efficient frontier, and walk-forward backtest vs S&P 500.

Live data via yfinance (cached for 10 minutes). The page is fully usable
without an FMP API key.
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
from portfolio.optimizer import (
    OptimizationResult,
    max_sharpe, min_vol, risk_parity, equal_weight, efficient_frontier,
)
from portfolio.shrinkage import ledoit_wolf
from portfolio.var_calculator import compute_risk_metrics, RiskMetrics
from portfolio.backtest import walk_forward
from ui.components.header_metric import render_header_metric
from ui.charts.efficient_frontier import build_frontier_figure
from ui.charts.drawdown_chart import build_backtest_figure


# ============================================================
# Page header + inputs
# ============================================================
st.markdown(
    '<div class="eq-section-label">PORTFOLIO OPTIMIZER</div>',
    unsafe_allow_html=True,
)

ic1, ic2, ic3, ic4 = st.columns([3, 1, 1, 1])
with ic1:
    tickers_raw = st.text_input(
        "Tickers", value="AAPL,MSFT,GOOGL,NVDA,AMZN,JPM,XOM,JNJ,KO,WMT",
        label_visibility="collapsed",
        placeholder="TICKERS (comma-separated)",
    )
with ic2:
    years = st.number_input(
        "Years", min_value=1, max_value=10, value=5, step=1,
        label_visibility="collapsed",
    )
with ic3:
    objective = st.selectbox(
        "Objective",
        ["Max Sharpe", "Min Vol", "Risk Parity", "Equal Weight"],
        label_visibility="collapsed",
    )
with ic4:
    optimize_btn = st.button(
        "Optimize", type="primary", use_container_width=True,
    )


# ============================================================
# Sidebar — risk controls
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
            help="Per-ticker floor. 0 lets the optimizer drop names entirely.",
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
            help="Share of the price history used to fit weights. Remainder is OOS.",
        )

    return {
        "risk_free": risk_free,
        "max_position": max_pos,
        "min_position": min_pos,
        "run_backtest": run_bt,
        "train_pct": train_pct,
    }


controls = _control_sidebar()


# ============================================================
# Main flow — guarded behind the Optimize button (with persistence)
# ============================================================
def _parse_tickers(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in raw.replace(";", ",").split(","):
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _objective_fn(name: str):
    return {
        "Max Sharpe":   max_sharpe,
        "Min Vol":      min_vol,
        "Risk Parity":  risk_parity,
        "Equal Weight": equal_weight,
    }[name]


def _objective_kwargs(name: str, controls: dict) -> dict:
    if name == "Equal Weight":
        return {"risk_free": controls["risk_free"]}
    base = {
        "risk_free":    controls["risk_free"],
        "max_position": controls["max_position"],
    }
    if name in ("Max Sharpe", "Min Vol"):
        base["min_position"] = controls["min_position"]
    return base


if optimize_btn or "po_loaded" in st.session_state:
    st.session_state["po_loaded"] = True

    tickers = _parse_tickers(tickers_raw)
    if len(tickers) < 2:
        st.error("Provide at least 2 tickers separated by commas.")
        st.stop()

    period = f"{int(years)}y"
    with st.spinner(f"Fetching {len(tickers)} tickers · {period} of daily prices…"):
        prices = get_price_panel(tuple(tickers), period=period, interval="1d")

    if prices is None or prices.empty:
        st.error(
            "No price data returned by yfinance. Check the tickers or try fewer "
            "years (intraday windows are smaller)."
        )
        st.stop()

    missing = [t for t in tickers if t not in prices.columns]
    if missing:
        st.warning(f"Dropped (no data): {', '.join(missing)}")
    prices = prices[[t for t in tickers if t in prices.columns]].dropna(how="any")

    if prices.shape[0] < 60 or prices.shape[1] < 2:
        st.error("Not enough overlapping price observations after cleaning.")
        st.stop()

    returns = prices.pct_change().dropna(how="any")

    # ---- Optimize ----
    fn = _objective_fn(objective)
    kwargs = _objective_kwargs(objective, controls)
    try:
        res: OptimizationResult = fn(returns, **kwargs)
    except Exception as exc:
        st.error(f"Optimization failed: {exc}")
        st.stop()

    if not res.converged and objective != "Equal Weight":
        st.warning(f"Optimizer did not fully converge: {res.message}")

    # ---- Header metrics ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        render_header_metric("EXPECTED RETURN", f"{res.expected_return:.2%}")
    with h2:
        render_header_metric("VOLATILITY",      f"{res.volatility:.2%}")
    with h3:
        render_header_metric("SHARPE",          f"{res.sharpe:.3f}")
    with h4:
        render_header_metric("ASSETS",
                             f"{int((res.weights > 1e-3).sum())} / {len(res.weights)}")

    # ---- Weights table ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">OPTIMAL WEIGHTS</div>',
        unsafe_allow_html=True,
    )
    weights_df = (
        res.weights
        .rename("Weight")
        .reset_index()
        .rename(columns={"index": "Ticker"})
        .assign(**{"Weight %": lambda d: d["Weight"] * 100})
        .sort_values("Weight", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(
        weights_df[["Ticker", "Weight %"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Weight %": st.column_config.ProgressColumn(
                format="%.2f%%", min_value=0.0, max_value=100.0,
            ),
        },
    )

    # ---- Efficient frontier ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
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

    cov = ledoit_wolf(returns).covariance
    asset_pts = pd.DataFrame({
        "return":     returns.mean() * 252,
        "volatility": np.sqrt(np.diag(cov.values)),
    }, index=returns.columns)

    selected = {
        "return":     res.expected_return,
        "volatility": res.volatility,
        "label":      objective,
    } if res.volatility > 0 else None

    st.plotly_chart(
        build_frontier_figure(ef, assets=asset_pts, selected=selected),
        use_container_width=True, config={"displayModeBar": False},
    )

    # ---- Risk metrics on the in-sample portfolio return ----
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">RISK METRICS · IN-SAMPLE</div>',
        unsafe_allow_html=True,
    )
    aligned = returns[res.weights.index]
    port_returns = (aligned * res.weights.values).sum(axis=1)
    rm: RiskMetrics = compute_risk_metrics(
        port_returns, risk_free_annual=controls["risk_free"],
    )
    risk_table = pd.DataFrame([
        {"Metric": "Annualized return",     "Value": f"{rm.annual_return:.2%}"},
        {"Metric": "Annualized volatility", "Value": f"{rm.annual_volatility:.2%}"},
        {"Metric": "Sharpe ratio",          "Value": f"{rm.sharpe:.3f}"},
        {"Metric": "Sortino ratio",         "Value": f"{rm.sortino:.3f}"},
        {"Metric": "Calmar ratio",          "Value": f"{rm.calmar:.3f}"},
        {"Metric": "Max drawdown",          "Value": f"{rm.max_drawdown:.2%}"},
        {"Metric": "VaR 95% (historical)",  "Value": f"{rm.var_95:.2%}"},
        {"Metric": "CVaR 95% (ES)",         "Value": f"{rm.cvar_95:.2%}"},
        {"Metric": "Skewness",              "Value": f"{rm.skewness:.2f}"},
        {"Metric": "Excess kurtosis",       "Value": f"{rm.kurtosis:.2f}"},
    ])
    st.dataframe(risk_table, hide_index=True, use_container_width=True)

    # ---- Walk-forward backtest ----
    if controls["run_backtest"]:
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="eq-section-label">WALK-FORWARD BACKTEST · vs S&P 500</div>',
            unsafe_allow_html=True,
        )
        bench_hist = get_spx_history(period=period)
        bench_close = (
            bench_hist["Close"].dropna() if "Close" in bench_hist.columns else None
        )
        try:
            bt = walk_forward(
                prices=prices,
                objective={
                    "Max Sharpe": "max_sharpe", "Min Vol": "min_vol",
                    "Risk Parity": "risk_parity", "Equal Weight": "equal_weight",
                }[objective],
                train_pct=controls["train_pct"],
                benchmark_prices=bench_close,
                optimizer_kwargs=kwargs,
            )
        except Exception as exc:
            st.warning(f"Backtest failed: {exc}")
        else:
            t1, t2, t3 = st.columns(3)
            with t1:
                render_header_metric(
                    "TRAIN WINDOW",
                    f"{bt.train_start.date()} → {bt.train_end.date()}",
                )
            with t2:
                render_header_metric(
                    "OOS WINDOW",
                    f"{bt.oos_start.date()} → {bt.oos_end.date()}",
                )
            with t3:
                final_port = float(bt.cumulative["portfolio"].iloc[-1])
                render_header_metric(
                    "OOS WEALTH (×)",
                    f"{final_port:,.3f}",
                )

            st.plotly_chart(
                build_backtest_figure(
                    bt.portfolio_returns,
                    benchmark_returns=bt.benchmark_returns,
                    portfolio_label=objective,
                    benchmark_label="S&P 500",
                ),
                use_container_width=True, config={"displayModeBar": False},
            )

            oos_port_metrics = compute_risk_metrics(
                bt.portfolio_returns, risk_free_annual=controls["risk_free"],
            )
            oos_summary = pd.DataFrame([
                {"Metric": "OOS annual return", "Value": f"{oos_port_metrics.annual_return:.2%}"},
                {"Metric": "OOS volatility",    "Value": f"{oos_port_metrics.annual_volatility:.2%}"},
                {"Metric": "OOS Sharpe",        "Value": f"{oos_port_metrics.sharpe:.3f}"},
                {"Metric": "OOS max DD",        "Value": f"{oos_port_metrics.max_drawdown:.2%}"},
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

    st.caption(
        "Live prices via yfinance (cached 10 min). Black-Litterman, GARCH "
        "vol, HRP and rolling rebalance are wired in their modules but not "
        "exposed in the UI yet."
    )

else:
    st.markdown(
        '<div class="eq-card" style="text-align:center; padding:48px 16px; '
        'color:var(--text-muted);">Configure tickers / objective and press '
        'Optimize.</div>',
        unsafe_allow_html=True,
    )
