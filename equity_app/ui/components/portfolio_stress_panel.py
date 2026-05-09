"""
Portfolio stress-testing tab for the Optimizer page.

Six sub-tabs: VaR · Historical · Hypothetical · Custom · Concentration ·
Correlation. Renders against the optimized weights from the parent page
plus a portfolio-value input ($1M default). Heavy computations are
upstream-cached (yfinance fetches via st.cache_data, ticker meta via a
24-hour cache) so flipping confidence levels or holding periods is cheap.

Distinct from ``stress_test_panel.py`` which stress-tests intrinsic
value (DCF rate / FX / recession / sector shocks) — that one lives on
the Valuation tab. This one operates on the realised return series of
an actual portfolio.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio.stress_test.data_prep import fetch_ticker_meta
from portfolio.stress_test.historical_scenarios import (
    run_all as run_historical_all,
)
from portfolio.stress_test.hypothetical_scenarios import (
    run_all as run_hypothetical_all,
    run_custom as run_hypothetical_custom,
)
from portfolio.stress_test.sensitivity import (
    beta_metrics,
    concentration_metrics,
    crisis_correlation,
    false_diversification_pairs,
)
from portfolio.stress_test.var_methods import compare_methods
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"


# ============================================================
# Helpers
# ============================================================
def _holdings_from_weights(
    weights: pd.Series,
    portfolio_value: float,
) -> tuple[dict[str, dict], dict[str, float]]:
    """Build {ticker: {weight, sector, beta, dollar_amount}} + dollars dict."""
    holdings: dict[str, dict] = {}
    dollars: dict[str, float] = {}
    for t, w in weights.items():
        try:
            wf = float(w)
        except (TypeError, ValueError):
            continue
        if wf <= 1e-6:
            continue
        meta = fetch_ticker_meta(t)
        dollar = wf * portfolio_value
        holdings[t] = {
            "weight": wf,
            "sector": meta.get("sector") or "Unknown",
            "beta": float(meta.get("beta", 1.0) or 1.0),
            "dollar_amount": dollar,
            "name": meta.get("name", t),
        }
        dollars[t] = dollar
    return holdings, dollars


def _metric_card(label: str, value: str, sub: str = "", *,
                 color: str = ACCENT) -> str:
    sub_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:11px; '
        f'margin-top:4px;">{sub}</div>' if sub else ""
    )
    return (
        f'<div style="background:{SURFACE}; border:1px solid {BORDER}; '
        f'border-top:3px solid {color}; border-radius:8px; padding:16px;">'
        f'<div style="color:{TEXT_MUTED}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:0.6px;">{label}</div>'
        f'<div style="color:{TEXT_PRIMARY}; font-size:22px; font-weight:500; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">{value}</div>'
        f'{sub_html}</div>'
    )


# ============================================================
# Public entry
# ============================================================
def render_portfolio_stress_panel(weights: pd.Series,
                                  prices: pd.DataFrame,
                                  returns: pd.DataFrame) -> None:
    if (weights is None or weights.empty
            or prices is None or prices.empty):
        st.info("Optimize the portfolio first — stress testing needs "
                "weights and prices.")
        return

    pc1, pc2 = st.columns([2, 6])
    with pc1:
        portfolio_value = float(st.number_input(
            "Portfolio value ($)",
            min_value=1_000.0, max_value=1_000_000_000.0,
            value=1_000_000.0, step=10_000.0, format="%.0f",
            key="st_portfolio_value",
        ))
    with pc2:
        n_active = int((weights > 1e-4).sum())
        st.caption(
            f"Stress tests applied to current optimized weights · "
            f"{n_active} positions"
        )

    with st.spinner("Resolving sector + beta for holdings…"):
        holdings, dollars = _holdings_from_weights(weights, portfolio_value)

    if not holdings:
        st.warning("No active positions in the optimized portfolio.")
        return

    cols = [t for t in holdings if t in returns.columns]
    if not cols:
        st.error("No overlap between optimized tickers and the returns matrix.")
        return
    w_series = pd.Series({t: holdings[t]["weight"] for t in cols})
    if w_series.sum() > 0:
        w_series = w_series / w_series.sum()
    portfolio_returns = (returns[cols] * w_series).sum(axis=1).dropna()

    sub = st.tabs([
        "VaR", "Historical", "Hypothetical", "Custom",
        "Concentration", "Correlation",
    ])

    with sub[0]:
        _render_var(portfolio_returns, portfolio_value)
    with sub[1]:
        _render_historical(dollars, portfolio_value)
    with sub[2]:
        _render_hypothetical(holdings, portfolio_value)
    with sub[3]:
        _render_custom(holdings, portfolio_value)
    with sub[4]:
        _render_concentration(holdings)
    with sub[5]:
        _render_correlation(returns[cols] if cols else returns)


# ============================================================
# Sub-tabs
# ============================================================
def _render_var(portfolio_returns: pd.Series, portfolio_value: float) -> None:
    st.markdown(
        '<div class="eq-section-label">VALUE AT RISK · 3 METHOD COMPARATOR</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        confidence = st.select_slider(
            "Confidence", options=[0.90, 0.95, 0.99], value=0.95,
            format_func=lambda x: f"{x*100:.0f}%",
            key="st_var_conf",
        )
    with c2:
        h = st.select_slider(
            "Holding period", options=[1, 5, 10, 20], value=1,
            format_func=lambda x: f"{x}d",
            key="st_var_h",
        )

    if len(portfolio_returns.dropna()) < 50:
        st.warning("Need at least 50 days of return history for VaR.")
        return

    res = compare_methods(portfolio_returns, portfolio_value=portfolio_value,
                          confidence=confidence, h=h)

    color = res["consensus_color"]
    div = res["divergence_pct"]
    div_str = "—" if not np.isfinite(div) else f"{div:.1f}%"
    st.markdown(
        f'<div style="background:{SURFACE}; border-left:3px solid {color}; '
        f'padding:12px 16px; border-radius:6px; margin:10px 0 16px 0;">'
        f'<div style="color:{color}; font-size:11px; text-transform:uppercase; '
        f'letter-spacing:0.6px;">Method convergence: {res["consensus"]}</div>'
        f'<div style="color:{TEXT_SECONDARY}; font-size:12px; margin-top:4px;">'
        f'Spread between methods: {div_str}</div></div>',
        unsafe_allow_html=True,
    )

    cols_m = st.columns(3)
    methods = [
        ("Historical",  res["historical"], cols_m[0], TEXT_SECONDARY),
        ("Parametric",  res["parametric"], cols_m[1], ACCENT),
        ("Monte Carlo", res["monte_carlo"], cols_m[2], GAINS),
    ]
    for name, data, col, c in methods:
        with col:
            if "error" in data:
                st.error(f"{name}: {data['error']}")
                continue
            var_p = abs(data["var_pct"])
            var_d = abs(data["var_dollar"])
            cvar_d = abs(data["cvar_dollar"])
            st.markdown(
                _metric_card(
                    f"{name} · VaR ({h}d, {confidence*100:.0f}%)",
                    f"-${var_d:,.0f}",
                    f"-{var_p:.2f}% · CVaR -${cvar_d:,.0f}",
                    color=c,
                ),
                unsafe_allow_html=True,
            )
            if name == "Parametric" and data.get("warning"):
                st.caption(f"⚠ {data['warning']}")
            elif name == "Monte Carlo":
                st.caption(
                    f"{data.get('n_simulations', 0):,} sims · "
                    f"{data.get('fitted_distribution', '')}"
                )

    mc = res["monte_carlo"]
    if "simulated_returns" in mc:
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        sims = mc["simulated_returns"]
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=sims * 100.0, nbinsx=80,
            marker_color=TEXT_SECONDARY, opacity=0.75, showlegend=False,
        ))
        fig.add_vline(x=mc["var_pct"], line_dash="dash", line_color=_DOWNSIDE,
                      annotation_text=f"VaR {mc['var_pct']:.2f}%",
                      annotation_position="top")
        fig.add_vline(x=mc["cvar_pct"], line_dash="dot", line_color=ACCENT,
                      annotation_text=f"CVaR {mc['cvar_pct']:.2f}%",
                      annotation_position="bottom")
        fig.update_layout(
            height=320, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
            xaxis=dict(title=f"{h}-day simulated return (%)",
                       gridcolor=BORDER, color=TEXT_MUTED),
            yaxis=dict(title="Frequency", gridcolor=BORDER, color=TEXT_MUTED),
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    with st.expander("How to read this"):
        st.markdown(
            f"**VaR ({confidence*100:.0f}%, {h}d)** says: with "
            f"{confidence*100:.0f}% confidence the portfolio won't lose "
            f"more than this in the next {h} day(s). "
            f"**CVaR** is the average loss when VaR is breached.\n\n"
            "**Why three methods?** Historical reflects past patterns; "
            "Parametric assumes normal returns (often understates fat tails); "
            "Monte Carlo with Student-t fits fat tails. Tight consensus → "
            "high confidence in the estimate. Wide spread → uncertainty about "
            "tail risk."
        )


def _render_historical(dollars: dict, portfolio_value: float) -> None:
    st.markdown(
        '<div class="eq-section-label">HISTORICAL CRISIS REPLAY</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Apply real crisis windows to current holdings. Tickers without "
        "a listing during a window are skipped — partial coverage is "
        "still reported."
    )

    with st.spinner("Replaying historical scenarios…"):
        results = run_historical_all(dollars, portfolio_value)

    valid = [r for r in results if "error" not in r]
    if not valid:
        st.error(
            "No scenarios produced data. Your ticker set may be too new "
            "for these windows — try broader, longer-listed names."
        )
        skipped = [r for r in results if "error" in r]
        if skipped:
            with st.expander("Errors"):
                for r in skipped:
                    st.caption(f"{r['scenario']}: {r['error']}")
        return

    fig = go.Figure()
    for r in valid:
        c = GAINS if r["portfolio_pct"] >= 0 else _DOWNSIDE
        fig.add_trace(go.Bar(
            x=[r["scenario"]], y=[r["portfolio_pct"]],
            marker_color=c, text=f"{r['portfolio_pct']:+.1f}%",
            textposition="outside", showlegend=False,
        ))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        yaxis=dict(title="Portfolio change (%)", gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(tickangle=-25, color=TEXT_MUTED),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    rows = []
    for r in valid:
        rows.append({
            "Scenario": r["scenario"],
            "Window": f"{r['start']} → {r['end']}",
            "Portfolio": f"{r['portfolio_pct']:+.2f}%",
            "Dollars": f"${r['portfolio_dollar']:+,.0f}",
            "Max DD": f"{r.get('portfolio_max_dd', 0):.2f}%",
            "vs SPY": (f"{r['alpha_vs_benchmark']:+.2f}%"
                       if r.get("alpha_vs_benchmark") is not None else "—"),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">PER-TICKER BREAKDOWN</div>',
        unsafe_allow_html=True,
    )
    names = [r["scenario"] for r in valid]
    pick = st.selectbox("Scenario", names, key="st_hist_pick",
                        label_visibility="collapsed")
    chosen = next(r for r in valid if r["scenario"] == pick)
    st.caption(f"{chosen['description']} · {chosen['start']} → {chosen['end']}")
    tr_rows = []
    for t, info in chosen["ticker_results"].items():
        tr_rows.append({
            "Ticker": t,
            "Weight": f"{info['weight']*100:.1f}%",
            "Change": f"{info['pct_change']:+.2f}%",
            "Max DD": f"{info['max_drawdown']:.2f}%",
            "$ Impact": float(info["dollar_impact"]),
        })
    if tr_rows:
        df = pd.DataFrame(tr_rows).sort_values("$ Impact")
        df["$ Impact"] = df["$ Impact"].map(lambda x: f"${x:+,.0f}")
        st.dataframe(df, hide_index=True, use_container_width=True)


def _render_hypothetical(holdings: dict, portfolio_value: float) -> None:
    st.markdown(
        '<div class="eq-section-label">HYPOTHETICAL MACRO SCENARIOS</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Forward-looking shocks applied per-holding via sector "
        "classification × CAPM beta."
    )

    results = run_hypothetical_all(holdings, portfolio_value)

    fig = go.Figure()
    for r in results:
        c = GAINS if r["portfolio_pct"] >= 0 else _DOWNSIDE
        fig.add_trace(go.Bar(
            x=[r["scenario"]], y=[r["portfolio_pct"]],
            marker_color=c, text=f"{r['portfolio_pct']:+.1f}%",
            textposition="outside", showlegend=False,
        ))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        yaxis=dict(title="Portfolio change (%)", gridcolor=BORDER, color=TEXT_MUTED),
        xaxis=dict(tickangle=-25, color=TEXT_MUTED),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    rows = []
    for r in results:
        rows.append({
            "Scenario": r["scenario"],
            "Description": r["description"],
            "Portfolio": f"{r['portfolio_pct']:+.2f}%",
            "Dollars": f"${r['portfolio_dollar']:+,.0f}",
            "New value": f"${r['new_value']:,.0f}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)


def _render_custom(holdings: dict, portfolio_value: float) -> None:
    st.markdown(
        '<div class="eq-section-label">CUSTOM SCENARIO BUILDER</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Define your own market and sector shocks; impact is computed "
        "from each holding's beta and sector classification."
    )

    market = st.slider(
        "Equity market shock (%)",
        min_value=-50.0, max_value=30.0, value=-15.0, step=1.0,
        key="st_custom_mkt",
    ) / 100.0

    with st.expander("Optional: per-sector overlays"):
        cs1, cs2, cs3 = st.columns(3)
        with cs1:
            tech = st.slider("Technology (%)", -60.0, 40.0, 0.0, 1.0,
                             key="st_custom_tech") / 100.0
            fin = st.slider("Financials (%)", -60.0, 40.0, 0.0, 1.0,
                            key="st_custom_fin") / 100.0
            disc = st.slider("Discretionary (%)", -60.0, 40.0, 0.0, 1.0,
                             key="st_custom_disc") / 100.0
        with cs2:
            energy = st.slider("Energy (%)", -60.0, 50.0, 0.0, 1.0,
                               key="st_custom_energy") / 100.0
            health = st.slider("Healthcare (%)", -50.0, 30.0, 0.0, 1.0,
                               key="st_custom_health") / 100.0
            staples = st.slider("Staples (%)", -40.0, 20.0, 0.0, 1.0,
                                key="st_custom_staples") / 100.0
        with cs3:
            re = st.slider("Real Estate (%)", -50.0, 30.0, 0.0, 1.0,
                           key="st_custom_re") / 100.0
            util = st.slider("Utilities (%)", -30.0, 20.0, 0.0, 1.0,
                             key="st_custom_util") / 100.0
            ind = st.slider("Industrials (%)", -50.0, 30.0, 0.0, 1.0,
                            key="st_custom_ind") / 100.0

    sectors: dict[str, float] = {}
    for k, v in {
        "tech": tech, "financials": fin, "discretionary": disc,
        "energy": energy, "healthcare": health, "staples": staples,
        "real_estate": re, "utilities": util, "industrials": ind,
    }.items():
        if abs(v) > 0:
            sectors[k] = v

    res = run_hypothetical_custom(holdings, portfolio_value,
                                   market=market, sectors=sectors)

    cards = st.columns(3)
    with cards[0]:
        c = GAINS if res["portfolio_pct"] >= 0 else _DOWNSIDE
        st.markdown(
            _metric_card("Portfolio impact",
                         f"{res['portfolio_pct']:+.2f}%",
                         f"${res['portfolio_dollar']:+,.0f}", color=c),
            unsafe_allow_html=True,
        )
    with cards[1]:
        st.markdown(
            _metric_card("New value", f"${res['new_value']:,.0f}", "",
                         color=ACCENT),
            unsafe_allow_html=True,
        )
    with cards[2]:
        st.markdown(
            _metric_card("Market shock", f"{market*100:+.1f}%", "",
                         color=TEXT_SECONDARY),
            unsafe_allow_html=True,
        )

    rows = []
    for t, info in res["ticker_impacts"].items():
        rows.append({
            "Ticker": t,
            "Weight": f"{info['weight']*100:.1f}%",
            "Sector": info["sector"],
            "Beta": f"{info['beta']:.2f}",
            "Impact": f"{info['pct_change']:+.2f}%",
            "$": f"${info['dollar_impact']:+,.0f}",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)


def _render_concentration(holdings: dict) -> None:
    st.markdown(
        '<div class="eq-section-label">CONCENTRATION RISK</div>',
        unsafe_allow_html=True,
    )

    metrics = concentration_metrics(holdings)
    bm = beta_metrics(holdings)
    if "error" in metrics:
        st.error(metrics["error"])
        return

    cards = st.columns(4)
    with cards[0]:
        st.markdown(_metric_card(
            "HHI", f"{metrics['hhi']:.0f}", metrics["verdict"],
            color=ACCENT,
        ), unsafe_allow_html=True)
    with cards[1]:
        st.markdown(_metric_card(
            "Top 3 weight", f"{metrics['top_3_pct']:.1f}%",
            f"Top 1 {metrics['top_1_pct']:.1f}% · "
            f"Top 5 {metrics['top_5_pct']:.1f}%",
            color=TEXT_SECONDARY,
        ), unsafe_allow_html=True)
    with cards[2]:
        st.markdown(_metric_card(
            "Effective N", f"{metrics['effective_n']:.1f}",
            f"of {metrics['n_positions']} positions",
            color=TEXT_SECONDARY,
        ), unsafe_allow_html=True)
    with cards[3]:
        beta_color = (GAINS if 0.85 <= bm["portfolio_beta"] < 1.15
                      else _DOWNSIDE if bm["portfolio_beta"] >= 1.15
                      else ACCENT)
        st.markdown(_metric_card(
            "Portfolio β",
            (f"{bm['portfolio_beta']:.2f}"
             if np.isfinite(bm["portfolio_beta"]) else "—"),
            bm["profile"], color=beta_color,
        ), unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">SECTOR EXPOSURE</div>',
        unsafe_allow_html=True,
    )
    sec_rows = [{"Sector": s, "Weight": f"{w*100:.1f}%"}
                for s, w in metrics.get("sector_breakdown", {}).items()]
    if sec_rows:
        st.dataframe(pd.DataFrame(sec_rows), hide_index=True,
                     use_container_width=True)

    st.caption(
        f"HHI: <1500 well diversified · 1500-2500 moderate · >2500 "
        f"concentrated. Largest sector is "
        f"{metrics.get('max_sector', '—')} at "
        f"{metrics.get('max_sector_pct', 0):.1f}%."
    )


def _render_correlation(returns: pd.DataFrame) -> None:
    st.markdown(
        '<div class="eq-section-label">CORRELATION DIAGNOSTICS</div>',
        unsafe_allow_html=True,
    )

    pairs = false_diversification_pairs(returns, threshold=0.80)
    crisis = crisis_correlation(returns, crisis_threshold=-0.02)

    if "error" not in crisis:
        cards = st.columns(3)
        with cards[0]:
            st.markdown(_metric_card(
                "Normal-day ρ̄",
                (f"{crisis['normal_corr']:.2f}"
                 if np.isfinite(crisis["normal_corr"]) else "—"),
                f"{crisis['n_normal']} obs",
                color=TEXT_SECONDARY,
            ), unsafe_allow_html=True)
        with cards[1]:
            spike_color = _DOWNSIDE if (np.isfinite(crisis["spike"]) and
                                         crisis["spike"] > 0.15) else ACCENT
            st.markdown(_metric_card(
                "Crisis-day ρ̄",
                (f"{crisis['crisis_corr']:.2f}"
                 if np.isfinite(crisis["crisis_corr"]) else "—"),
                f"{crisis['n_crisis']} obs",
                color=spike_color,
            ), unsafe_allow_html=True)
        with cards[2]:
            spike_v = crisis["spike"]
            verdict = ("breaks down" if (np.isfinite(spike_v) and spike_v > 0.15)
                       else "holds up")
            st.markdown(_metric_card(
                "Correlation spike",
                (f"{spike_v:+.2f}" if np.isfinite(spike_v) else "—"),
                f"diversification {verdict} in stress",
                color=(_DOWNSIDE if verdict == "breaks down" else GAINS),
            ), unsafe_allow_html=True)
    else:
        st.info(f"Crisis correlation: {crisis['error']}")

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">FALSE-DIVERSIFICATION PAIRS · ρ > 0.80</div>',
        unsafe_allow_html=True,
    )
    if not pairs:
        st.success("No high-correlation pairs above the 0.80 threshold.")
    else:
        st.dataframe(pd.DataFrame([
            {"Asset A": p["a"], "Asset B": p["b"], "ρ": f"{p['rho']:.2f}"}
            for p in pairs[:20]
        ]), hide_index=True, use_container_width=True)
