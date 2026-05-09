"""
Position-sizing helper (P11.B3).

Inline expander on the Equity Analysis page. Three knobs (portfolio
size, max position %, conviction 1-5) plus a hidden vol penalty for
high-volatility names.

Sizing formula:
    target_pct = max_position_pct × conviction_factor × vol_factor

    conviction_factor: 1 → 0.25, 2 → 0.4375, 3 → 0.625, 4 → 0.8125, 5 → 1.0
    vol_factor:        0.30 / vol, clipped to [0.4, 1.0]
                       (i.e. names ≤30% vol get full size, beyond that
                        start scaling down — a 60% vol name caps at 0.5x)

Annual vol is computed from the cached price panel (1y daily returns,
std × √252). Caller passes the active ticker + current price.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import streamlit as st


@st.cache_data(ttl=600, show_spinner=False)
def _annualised_vol(ticker: str) -> Optional[float]:
    try:
        from data.market_data import get_price_panel
        panel = get_price_panel((ticker,), period="1y", interval="1d")
        if panel is None or panel.empty or ticker not in panel.columns:
            return None
        returns = panel[ticker].pct_change().dropna()
        if len(returns) < 30:
            return None
        return float(returns.std(ddof=1) * np.sqrt(252.0))
    except Exception:
        return None


def render_position_sizing_card(ticker: str, current_price: Optional[float]) -> None:
    """Inline sizing helper. Renders inside an expander to keep the page
    dense — opens only when the user is mid-decision."""
    if not current_price or current_price <= 0:
        return                               # no price → no sizing math

    with st.expander("💼 Position sizing (for actual purchases)",
                     expanded=False):
        c1, c2, c3 = st.columns(3)
        portfolio_value = c1.number_input(
            "Portfolio total ($)",
            min_value=1_000.0, value=100_000.0, step=5_000.0,
            format="%.0f", key=f"posize_pv_{ticker}",
        )
        max_position_pct = c2.slider(
            "Max position (% of portfolio)",
            min_value=2, max_value=20, value=8,
            key=f"posize_max_{ticker}",
        ) / 100.0
        conviction = int(c3.select_slider(
            "Conviction (1=low, 5=high)",
            options=[1, 2, 3, 4, 5], value=3,
            key=f"posize_conv_{ticker}",
        ))

        vol = _annualised_vol(ticker)
        vol_for_calc = vol if vol is not None else 0.30
        # Conviction factor: 1 → 0.25, 5 → 1.0 (linear in 0.1875 increments)
        conviction_factor = 0.25 + (conviction - 1) * 0.1875
        # Vol penalty: 30% vol = 1.0x, 60% vol = 0.5x, floor 0.4
        vol_factor = max(0.4, min(1.0, 0.30 / vol_for_calc)) if vol_for_calc > 0 else 1.0

        target_pct = max_position_pct * conviction_factor * vol_factor
        target_dollars = portfolio_value * target_pct
        target_shares = int(target_dollars / current_price)

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Suggested allocation",
            f"${target_dollars:,.0f}",
            help=f"{target_pct*100:.1f}% of portfolio",
        )
        m2.metric(
            "Shares to buy",
            f"{target_shares:,}",
            help=f"@ ${current_price:.2f}",
        )
        m3.metric(
            "Volatility (1y)",
            f"{vol*100:.1f}%" if vol is not None else "—",
            help=("Annualised std dev of daily returns. Names above 30% "
                  "vol get sized down via vol_factor.")
                 if vol is not None else
                 "Could not compute — using 30% default for sizing.",
        )

        st.caption(
            f"Max {max_position_pct*100:.0f}% × "
            f"Conviction {conviction_factor:.2f} × "
            f"Vol {vol_factor:.2f} = **{target_pct*100:.2f}%** target weight."
        )
