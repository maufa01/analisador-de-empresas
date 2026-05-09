"""
Multi-multiple forward valuation panel.

Renders the matrix the user keeps in their Excel: rows = projected
years (FY+1 … FY+N), cols = P/E · P/FCF · EV/EBITDA · P/S · P/B · Avg ·
PV. Plus a peers-used expander showing each peer's individual multiple
and the medians the engine consumed.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from valuation.multi_multiple import run_multi_multiple_valuation
from ui.theme import (
    ACCENT, BORDER, GAINS, SURFACE,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


_DOWNSIDE = "rgba(184,115,51,1)"


def render_multi_multiple_valuation_panel(
    *,
    target_ticker: str,
    current_price: float,
    forecast_result,
    peer_snapshots: list,
    shares_outstanding: float,
    discount_rate: float = 0.12,
) -> None:
    if not peer_snapshots:
        st.info(
            "Multi-multiple valuation requires peers — none configured "
            "for this ticker."
        )
        return
    if (forecast_result is None
            or forecast_result.income_projected is None
            or forecast_result.income_projected.empty):
        st.info(
            "Multi-multiple valuation requires a forecast — load the "
            "Forecast tab first to populate it."
        )
        return
    if not shares_outstanding or shares_outstanding <= 0:
        st.info(
            "Multi-multiple valuation needs shares outstanding "
            "(unavailable from data sources for this ticker)."
        )
        return

    # ---- Discount-rate slider ----
    c1, _ = st.columns([1, 3])
    with c1:
        dr = float(st.number_input(
            "Discount rate",
            min_value=0.05, max_value=0.20,
            value=float(discount_rate), step=0.005, format="%.3f",
            help="Used to discount future implied prices back to PV. "
                 "12% is a reasonable default for US large-cap equity; "
                 "lower for utilities, higher for small / risky names.",
            key=f"mm_dr_{target_ticker}",
        ))

    result = run_multi_multiple_valuation(
        target_ticker=target_ticker,
        current_price=current_price,
        forecast_result=forecast_result,
        peer_snapshots=peer_snapshots,
        shares_outstanding=shares_outstanding,
        discount_rate=dr,
    )

    # ---- Header summary cards ----
    if current_price and current_price > 0:
        upside_avg = (result.grand_average_price / current_price - 1.0) * 100.0
        upside_pv = (result.grand_pv_average / current_price - 1.0) * 100.0
    else:
        upside_avg = upside_pv = 0.0

    h1, h2, h3 = st.columns(3)
    h1.metric("Current price", f"${current_price:.2f}")
    h2.metric(
        "Avg implied (forward)",
        f"${result.grand_average_price:.2f}",
        delta=f"{upside_avg:+.1f}%",
    )
    h3.metric(
        f"Avg PV @ {dr*100:.1f}%",
        f"${result.grand_pv_average:.2f}",
        delta=f"{upside_pv:+.1f}%",
    )

    # ---- Year × multiple matrix ----
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="eq-section-label">IMPLIED PRICE BY MULTIPLE × YEAR</div>',
        unsafe_allow_html=True,
    )

    if not result.years_forward:
        st.info(
            "Forecast horizon doesn't extend past today — nothing to "
            "valuate. Increase the forecast Years slider on the Forecast tab."
        )
        return

    rows: list[dict] = []
    for yr in result.years_forward:
        row: dict[str, str] = {"Year": str(yr.year)}
        for v in yr.valuations:
            row[v.multiple_name] = (f"${v.implied_price:.2f}"
                                    if v.implied_price else "—")
        row["Avg"] = (f"${yr.average_price:.2f}"
                      if yr.average_price > 0 else "—")
        row["PV"] = (f"${yr.pv_discounted:.2f}"
                     if yr.pv_discounted > 0 else "—")
        row["CAGR vs current"] = (
            f"{yr.cagr_to_current*100:+.1f}%"
            if yr.cagr_to_current is not None else "—"
        )
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.caption(
        "Each cell = peer median multiple × target's projected metric. "
        "The 5 multiples often diverge 50%+ — that divergence IS the "
        "information. PV discounts the average back to today."
    )

    # ---- Peer multiples expander ----
    with st.expander("Peer multiples used (medians)"):
        peer_rows: list[dict] = []
        for p in peer_snapshots:
            mcap = getattr(p, "market_cap", None)
            ni = getattr(p, "net_income", None)
            rev = getattr(p, "revenue", None)
            ebitda = getattr(p, "ebitda", None)
            bv = getattr(p, "book_value", None)
            ev = getattr(p, "enterprise_value", None) or mcap

            def _r(num, denom):
                if not num or not denom or denom <= 0:
                    return "—"
                return f"{num/denom:.1f}x"

            peer_rows.append({
                "Ticker":    p.ticker,
                "P/E":       _r(mcap, ni),
                "EV/EBITDA": _r(ev, ebitda),
                "P/S":       _r(mcap, rev),
                "P/B":       _r(mcap, bv),
            })
        st.dataframe(pd.DataFrame(peer_rows), hide_index=True,
                     use_container_width=True)

        st.markdown(
            '<div class="eq-section-label" style="margin-top:10px;">'
            'PEER MEDIANS (used in calc)</div>',
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4, m5 = st.columns(5)
        def _f(v):
            return f"{v:.1f}x" if v else "—"
        m1.metric("P/E",       _f(result.peer_pe_median))
        m2.metric("P/FCF",     _f(result.peer_pfcf_median))
        m3.metric("EV/EBITDA", _f(result.peer_ev_ebitda_median))
        m4.metric("P/S",       _f(result.peer_ps_median))
        m5.metric("P/B",       _f(result.peer_pb_median))
