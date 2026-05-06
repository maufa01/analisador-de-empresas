"""
13F superinvestors panel — selector + quick filings index +
gated 'Load latest holdings' button (parses one InfoTable XML).

Cached on disk for 7 days through ``fetch_full_13f_holdings_cached``.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from data.edgar_provider import (
    FAMOUS_INVESTORS,
    get_13f_summary_for_investor,
    fetch_full_13f_holdings_cached,
)


def _fmt_billions(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12: return f"{sign}${av/1e12:,.2f}T"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.0f}M"
    return f"{sign}${av:,.0f}"


def render_superinvestors_panel() -> None:
    st.markdown(
        '<div class="eq-section-label">13F · FAMOUS INVESTORS</div>',
        unsafe_allow_html=True,
    )

    # ---- Investor selector ----
    options = {info["name"]: key for key, info in FAMOUS_INVESTORS.items()}
    label = st.selectbox(
        "Investor",
        list(options.keys()),
        index=0,
        key="superinvestor_select",
    )
    investor_key = options[label]

    # ---- Quick summary (1 SEC call) ----
    with st.spinner("Loading 13F filings index…"):
        try:
            summary = get_13f_summary_for_investor(investor_key)
        except Exception as e:
            st.markdown(
                '<div class="eq-card" style="padding:18px; '
                'color:var(--text-muted); font-size:13px;">'
                f'SEC request failed: {e}</div>',
                unsafe_allow_html=True,
            )
            return

    if not summary.get("available") or summary["total_filings"] == 0:
        st.info("No 13F-HR filings found for this investor.")
        return

    last_filed = summary["last_filing_date"]
    last_str = last_filed.strftime("%Y-%m-%d") if isinstance(last_filed, pd.Timestamp) else "—"

    c1, c2, c3 = st.columns(3, gap="small")
    c1.metric("INVESTOR", summary["investor_name"][:22])
    c2.metric("13F-HR FILINGS", str(summary["total_filings"]))
    c3.metric("LATEST FILING", last_str)

    # Filings list (metadata only)
    filings = summary["filings"]
    if not filings.empty:
        with st.expander("Recent 13F filings (metadata only — not yet parsed)",
                         expanded=False):
            f = filings.head(8).copy()
            keep = [c for c in ("filing_date", "report_date",
                                 "accession_number") if c in f.columns]
            f = f[keep]
            if "filing_date" in f.columns:
                f["filing_date"] = f["filing_date"].dt.strftime("%Y-%m-%d")
            if "report_date" in f.columns:
                f["report_date"] = f["report_date"].apply(
                    lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "—"
                )
            f = f.rename(columns={
                "filing_date":      "Filed",
                "report_date":      "Period",
                "accession_number": "Accession",
            })
            st.dataframe(f, hide_index=True, use_container_width=True)

    # ---- UI gate for the holdings parse ----
    state_key = f"_13f_loaded_{investor_key}"

    if st.session_state.get(state_key) is True:
        with st.spinner("Parsing latest 13F-HR InfoTable XML… (cached 7 days)"):
            holdings = fetch_full_13f_holdings_cached(investor_key, which="latest")
        if holdings.empty:
            st.warning("Holdings parse returned no rows.")
            return

        total_value = float(holdings["value_usd"].dropna().sum()) if "value_usd" in holdings.columns else None
        n_holdings = len(holdings)

        h1, h2, h3 = st.columns(3, gap="small")
        h1.metric("HOLDINGS", str(n_holdings))
        h2.metric("PORTFOLIO VALUE", _fmt_billions(total_value))
        h3.metric("TOP 10 SHARE",
                  f"{holdings.head(10)['weight_pct'].sum():.1f}%"
                  if "weight_pct" in holdings.columns else "—")

        st.markdown(
            '<div class="eq-section-label" style="margin-top:12px;">'
            'TOP 25 HOLDINGS BY VALUE</div>',
            unsafe_allow_html=True,
        )
        show = holdings.head(25).copy()
        if "value_usd" in show.columns:
            show["value_usd"] = show["value_usd"].apply(_fmt_billions)
        if "shares" in show.columns:
            show["shares"] = show["shares"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
            )
        if "weight_pct" in show.columns:
            show["weight_pct"] = show["weight_pct"].apply(
                lambda x: f"{x:.2f}%" if pd.notna(x) else "—"
            )
        keep = [c for c in ("name_of_issuer", "cusip", "shares",
                             "value_usd", "weight_pct") if c in show.columns]
        show = show[keep].rename(columns={
            "name_of_issuer": "Issuer",
            "cusip":          "CUSIP",
            "shares":         "Shares",
            "value_usd":      "Value",
            "weight_pct":     "Weight",
        })
        st.dataframe(show, hide_index=True, use_container_width=True)

        if st.button("Refresh holdings (re-parse)",
                     key=f"refresh_13f_{investor_key}",
                     help="Drops the 7-day cache and re-parses the latest InfoTable XML."):
            try:
                from data.cache import cache_clear
                cache_clear("sec_13f_holdings")
            except Exception:
                pass
            st.session_state[state_key] = False
            st.rerun()
        return

    st.markdown(
        '<div class="eq-card" style="padding:20px 22px; margin-top:12px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">LOAD LATEST HOLDINGS</div>'
        '<div style="color:var(--text-secondary); font-size:13px; '
        'margin-top:8px; line-height:1.5;">'
        'Parses the InfoTable XML of the latest 13F-HR filing — typically '
        '50–500 holdings depending on the manager.'
        '</div>'
        '<div style="color:var(--text-muted); font-size:11px; margin-top:10px;">'
        '⚠ Single SEC request, but the XML can be large. Result cached '
        'for 7 days per investor.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.button("Load latest 13F holdings",
                 type="primary",
                 key=f"load_13f_{investor_key}"):
        st.session_state[state_key] = True
        st.rerun()
