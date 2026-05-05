"""
Portfolio optimizer — placeholder with the new theme.

Full Markowitz / Black-Litterman / Ledoit-Wolf wiring lands in Session 4.
This page exists so the top navigation has a destination.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st


st.markdown(
    '<div class="eq-section-label">PORTFOLIO OPTIMIZER</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="eq-card" style="padding:24px;">
        <div class="eq-header-label">Coming in Session 4</div>
        <div style="margin-top: 10px; color: var(--text-secondary); font-size: 13px;">
            Markowitz mean-variance with Ledoit-Wolf shrinkage,
            Black-Litterman with user views, HRP, sector caps, position
            limits, walk-forward backtest vs S&amp;P 500 / 60-40.
        </div>
        <div style="margin-top: 14px; color: var(--text-muted); font-size: 12px;">
            Estimators: historical · CAPM-implied · Black-Litterman · EWM<br>
            Optimizations: Max Sharpe · Min Vol · Max Sortino · Risk Parity · HRP<br>
            Risk metrics: Sharpe · Sortino · Max DD · VaR95 · CVaR95
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("Quick portfolio (legacy v1)", expanded=False):
    tickers = st.text_input(
        "Tickers (comma-separated)",
        value="AAPL,MSFT,GOOGL,JNJ,XOM,JPM,KO",
    )
    rf = st.number_input("Risk-free rate", value=0.045, step=0.005, format="%.3f")
    years = st.number_input("Years of history", value=5, min_value=1, max_value=10)
    if st.button("Optimize", use_container_width=False):
        st.info(
            "The legacy v1 markowitz module is still available at the repo root. "
            "Native v2 wiring with PyPortfolioOpt arrives in Session 4."
        )
