"""
Streamlit dashboard.

Run:
    streamlit run app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from fetcher import fetch_data, fetch_peers, fetch_price_panel
from ratios import calculate_ratios
from dcf import dcf_model, build_dcf_inputs_from_company, calculate_wacc, sensitivity_table
from comparables import comparables_model
from scoring import scoring_model
from markowitz import (
    expected_returns, covariance_matrix,
    optimize_max_sharpe, optimize_min_vol, efficient_frontier,
)
from config import DEFAULT_WACC_PARAMS, DCF_DEFAULTS, PORTFOLIO_DEFAULTS

st.set_page_config(page_title="Equity Research", layout="wide")
st.title("📊 Equity Research + Portfolio Optimizer")

tab_stock, tab_pf = st.tabs(["🔎 Análisis de empresa", "📈 Optimización de portfolio"])

# ============================================================
# TAB 1 — Single Stock
# ============================================================
with tab_stock:
    c1, c2 = st.columns([1, 2])
    with c1:
        ticker = st.text_input("Ticker target", value="AAPL").strip().upper()
    with c2:
        peers_input = st.text_input(
            "Peers (separados por coma)", value="MSFT,GOOGL,META"
        )

    with st.sidebar:
        st.header("⚙️ Parámetros DCF")
        beta = st.number_input("Beta", value=1.20, step=0.10)
        rf = st.number_input(
            "Risk-free rate", value=DEFAULT_WACC_PARAMS["risk_free_rate"],
            step=0.005, format="%.3f",
        )
        erp = st.number_input(
            "Equity Risk Premium", value=DEFAULT_WACC_PARAMS["market_risk_premium"],
            step=0.005, format="%.3f",
        )
        kd = st.number_input(
            "Cost of debt (pre-tax)", value=DEFAULT_WACC_PARAMS["cost_of_debt"],
            step=0.005, format="%.3f",
        )
        tax = st.number_input(
            "Tax rate", value=DEFAULT_WACC_PARAMS["tax_rate"],
            step=0.05, format="%.2f",
        )
        we = st.slider("Weight equity", 0.0, 1.0, DEFAULT_WACC_PARAMS["weight_equity"])
        wd = 1 - we
        st.caption(f"Weight debt = {wd:.2f}")

        st.header("Proyección")
        proj_years = st.slider("Años proyección", 3, 10, DCF_DEFAULTS["projection_years"])
        tg = st.number_input(
            "Terminal growth", value=DCF_DEFAULTS["terminal_growth"],
            step=0.005, format="%.3f",
        )
        manual_g = st.number_input(
            "Override growth FCF (0 = usar CAGR)", value=0.0, step=0.01, format="%.2f",
        )

    if st.button("🔍 Analizar", type="primary"):
        with st.spinner(f"Bajando datos de {ticker} y peers..."):
            try:
                target = fetch_data(ticker)
                peer_tk = [t.strip() for t in peers_input.split(",") if t.strip()]
                peers_data = fetch_peers(peer_tk)
                peers_list = list(peers_data.values())
            except Exception as e:
                st.error(f"Error al fetchear datos: {e}")
                st.stop()

        # ----- RATIOS -----
        ratios_df = calculate_ratios(
            target.income_stmt, target.balance_sheet, target.cash_flow
        )

        # ----- WACC + DCF -----
        wacc = calculate_wacc(beta, rf, erp, kd, tax, we, wd)
        dcf_res = None
        intrinsic_dcf = None
        try:
            dcf_inputs = build_dcf_inputs_from_company(
                target, wacc=wacc, terminal_growth=tg,
                projection_years=proj_years,
                growth_rate=manual_g if manual_g != 0 else None,
            )
            dcf_res = dcf_model(dcf_inputs)
            intrinsic_dcf = dcf_res.intrinsic_per_share
        except Exception as e:
            st.warning(f"DCF no calculable: {e}")

        # ----- COMPARABLES -----
        comps = None
        intrinsic_comps = None
        try:
            comps = comparables_model(target, peers_list)
            intrinsic_comps = comps["average_implied"]
        except Exception as e:
            st.warning(f"Comparables no calculable: {e}")

        # ----- INTRÍNSECO PROMEDIO -----
        candidates = [
            v for v in [intrinsic_dcf, intrinsic_comps]
            if v is not None and pd.notna(v)
        ]
        intrinsic_avg = sum(candidates) / len(candidates) if candidates else None
        price = target.current_price

        # ----- SCORING -----
        score = scoring_model(ratios_df, price, intrinsic_avg) if intrinsic_avg else None

        # ============ HEADER METRICS ============
        st.subheader(f"{target.info.get('longName', ticker)} ({ticker})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💵 Precio actual", f"${price:.2f}" if price else "—")
        m2.metric("🎯 Valor intrínseco", f"${intrinsic_avg:.2f}" if intrinsic_avg else "—")
        if score:
            up = score["upside"] * 100
            m3.metric("📊 Upside", f"{up:+.1f}%", delta=f"{up:+.1f}%")
            m4.metric("⭐ Rating", score["rating"])

        # ============ DCF & COMPS DETALLE ============
        col_dcf, col_comp = st.columns(2)

        with col_dcf:
            st.markdown("### 💰 DCF")
            if dcf_res:
                st.write(f"**WACC:** {wacc:.2%}")
                st.write(f"**Growth usado:** {dcf_res.growth_used:.2%}")
                st.write(f"**Terminal growth:** {tg:.2%}")
                st.write(f"**EV:** ${dcf_res.enterprise_value/1e9:,.1f}B")
                st.write(f"**Equity Value:** ${dcf_res.equity_value/1e9:,.1f}B")
                st.write(f"**Intrínseco/acción:** ${intrinsic_dcf:.2f}")
                df_proj = pd.DataFrame({
                    "FCF Proyectado": dcf_res.projected_fcf,
                    "PV": dcf_res.pv_fcf,
                })
                st.dataframe(df_proj.style.format("{:,.0f}"), use_container_width=True)
                
                # Sensibilidad
                with st.expander("🔬 Sensibilidad WACC vs g terminal"):
                    try:
                        sens = sensitivity_table(dcf_inputs)
                        st.dataframe(sens.style.format("${:.2f}").background_gradient(cmap="RdYlGn"))
                    except Exception as e:
                        st.warning(f"Sensibilidad no calculable: {e}")

        with col_comp:
            st.markdown("### 📊 Comparables")
            if comps:
                st.write(f"**Precio implícito (promedio):** ${intrinsic_comps:.2f}")
                st.dataframe(
                    comps["implied_prices"].to_frame().style.format("${:,.2f}"),
                    use_container_width=True,
                )
                st.markdown("**Estadísticos del peer group:**")
                st.dataframe(
                    comps["peer_stats"].T.style.format("{:.2f}"),
                    use_container_width=True,
                )
                with st.expander("Ver tabla completa de peers"):
                    st.dataframe(comps["peers_table"].style.format("{:,.2f}", na_rep="—"))

        # ============ GRÁFICOS ============
        st.markdown("### 📈 Históricos")
        gc1, gc2 = st.columns(2)
        with gc1:
            if "Revenue" in ratios_df.columns:
                fig = px.bar(ratios_df, y="Revenue", title="Revenue histórico")
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
        with gc2:
            if "FCF" in ratios_df.columns:
                fig = px.bar(ratios_df, y="FCF", title="Free Cash Flow histórico")
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

        gc3, gc4 = st.columns(2)
        with gc3:
            if "EBITDA Margin %" in ratios_df.columns:
                fig = px.line(
                    ratios_df, y="EBITDA Margin %", markers=True,
                    title="EBITDA Margin %",
                )
                st.plotly_chart(fig, use_container_width=True)
        with gc4:
            if "ROE %" in ratios_df.columns:
                fig = px.line(ratios_df, y="ROE %", markers=True, title="ROE %")
                st.plotly_chart(fig, use_container_width=True)

        # Precio vs intrínseco
        if not target.prices.empty and intrinsic_avg:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=target.prices.index, y=target.prices["Close"],
                name="Precio", line=dict(color="#2196F3"),
            ))
            fig.add_hline(
                y=intrinsic_avg, line_dash="dash", line_color="red",
                annotation_text=f"Intrínseco ${intrinsic_avg:.2f}",
            )
            fig.update_layout(title="Precio histórico vs Valor Intrínseco",
                              xaxis_title="", yaxis_title="USD")
            st.plotly_chart(fig, use_container_width=True)

        # ============ RATIOS TABLA ============
        st.markdown("### 📋 Tabla de Ratios")
        st.dataframe(ratios_df.style.format("{:.2f}", na_rep="—"), use_container_width=True)

        # ============ SCORE BREAKDOWN ============
        if score:
            st.markdown("### 🎯 Score breakdown")
            st.write(f"**Score total:** {score['score']}/100")
            comp_df = pd.DataFrame(
                score["components"], index=["Score"]
            ).T.rename(columns={"Score": "0-100"})
            st.bar_chart(comp_df)

# ============================================================
# TAB 2 — Portfolio Markowitz
# ============================================================
with tab_pf:
    st.subheader("Optimización Markowitz")
    pf_input = st.text_input(
        "Tickers (separados por coma)",
        value="AAPL,MSFT,GOOGL,JNJ,XOM,JPM,KO",
    )
    rf_pf = st.number_input(
        "Risk-free rate", value=PORTFOLIO_DEFAULTS["risk_free_rate"],
        step=0.005, format="%.3f", key="rf_pf",
    )
    years_pf = st.slider("Años de histórico", 1, 10, 5)
    allow_short = st.checkbox("Permitir short selling", value=False)

    if st.button("📈 Optimizar", type="primary"):
        tickers = [t.strip().upper() for t in pf_input.split(",") if t.strip()]
        if len(tickers) < 2:
            st.error("Necesitás al menos 2 tickers.")
            st.stop()
        
        with st.spinner("Bajando precios..."):
            prices = fetch_price_panel(tickers, years=years_pf).dropna()
        
        if prices.empty:
            st.error("No se obtuvieron precios.")
            st.stop()

        mu = expected_returns(prices)
        cov = covariance_matrix(prices)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Retornos esperados (anualizados)**")
            st.dataframe((mu * 100).round(2).to_frame("Return %"))
        with c2:
            st.markdown("**Matriz de covarianza (anualizada)**")
            st.dataframe(cov.round(4))

        # Optimizaciones
        try:
            sharpe_p = optimize_max_sharpe(mu, cov, risk_free=rf_pf, allow_short=allow_short)
            minvol_p = optimize_min_vol(mu, cov, allow_short=allow_short)
        except Exception as e:
            st.error(f"Optimización falló: {e}")
            st.stop()

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### ⭐ Max Sharpe")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Retorno", f"{sharpe_p['return']*100:.2f}%")
            mc2.metric("Volatilidad", f"{sharpe_p['volatility']*100:.2f}%")
            mc3.metric("Sharpe", f"{sharpe_p['sharpe']:.3f}")
            st.dataframe((sharpe_p["weights"] * 100).round(2).to_frame("Weight %"))
        with c4:
            st.markdown("### 🛡️ Min Vol")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Retorno", f"{minvol_p['return']*100:.2f}%")
            mc2.metric("Volatilidad", f"{minvol_p['volatility']*100:.2f}%")
            mc3.metric("Sharpe", f"{minvol_p['sharpe']:.3f}")
            st.dataframe((minvol_p["weights"] * 100).round(2).to_frame("Weight %"))

        # Frontera eficiente
        with st.spinner("Construyendo frontera eficiente..."):
            frontier = efficient_frontier(mu, cov, n_points=40, allow_short=allow_short)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=frontier["volatility"] * 100,
            y=frontier["return"] * 100,
            mode="lines+markers", name="Frontera Eficiente",
            line=dict(color="#1f77b4"),
        ))
        fig.add_trace(go.Scatter(
            x=[sharpe_p["volatility"] * 100],
            y=[sharpe_p["return"] * 100],
            mode="markers+text",
            marker=dict(size=18, color="red", symbol="star"),
            text=["Max Sharpe"], textposition="top center",
            name="Max Sharpe",
        ))
        fig.add_trace(go.Scatter(
            x=[minvol_p["volatility"] * 100],
            y=[minvol_p["return"] * 100],
            mode="markers+text",
            marker=dict(size=15, color="green", symbol="diamond"),
            text=["Min Vol"], textposition="bottom center",
            name="Min Vol",
        ))
        # Activos individuales
        ind_vol = (cov.values.diagonal() ** 0.5) * 100
        fig.add_trace(go.Scatter(
            x=ind_vol, y=mu.values * 100, mode="markers+text",
            marker=dict(size=10, color="grey"),
            text=mu.index.tolist(), textposition="top center",
            name="Activos individuales",
        ))
        fig.update_layout(
            title="Frontera Eficiente",
            xaxis_title="Volatilidad anualizada %",
            yaxis_title="Retorno esperado anualizado %",
            height=550,
        )
        st.plotly_chart(fig, use_container_width=True)
