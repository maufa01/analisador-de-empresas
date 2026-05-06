"""
Congressional trading panel (Finnhub /stock/congressional-trading).

Shows recent transactions by US senators / representatives in this
ticker, with party + amount range + transaction type.

Renders an empty 'configure FINNHUB_API_KEY' state when no key.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_range(amount_from, amount_to) -> str:
    if pd.isna(amount_from) and pd.isna(amount_to):
        return "—"
    a = (f"${amount_from:,.0f}"
         if isinstance(amount_from, (int, float)) and not pd.isna(amount_from)
         else "—")
    b = (f"${amount_to:,.0f}"
         if isinstance(amount_to, (int, float)) and not pd.isna(amount_to)
         else "—")
    return f"{a}–{b}"


def render_senate_trading_panel(ticker: str) -> None:
    try:
        from data.finnhub_provider import is_available, fetch_senate_trading
    except Exception:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">CONGRESSIONAL TRADES</span>'
            '<div style="margin-top:8px;">finnhub_provider module unavailable.</div></div>',
            unsafe_allow_html=True,
        )
        return

    if not is_available():
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">CONGRESSIONAL TRADES</span>'
            '<div style="margin-top:8px;">FINNHUB_API_KEY not configured.</div></div>',
            unsafe_allow_html=True,
        )
        return

    with st.spinner("Loading congressional trading data…"):
        try:
            df = fetch_senate_trading(ticker)
        except Exception as e:
            st.warning(f"Finnhub request failed: {e}")
            return

    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">CONGRESSIONAL TRADES</span>'
            f'<div style="margin-top:8px;">No congressional trades reported '
            f'for {ticker}.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # ---- Summary ----
    n_total = len(df)
    n_unique = df["name"].nunique() if "name" in df.columns else 0
    last_date = (df["transactionDate"].max().strftime("%Y-%m-%d")
                 if "transactionDate" in df.columns
                 and not df["transactionDate"].dropna().empty else "—")

    purchase_mask = (df["transactionType"].astype(str).str.lower()
                     .str.contains("purchase", na=False)
                     if "transactionType" in df.columns else None)
    sale_mask = (df["transactionType"].astype(str).str.lower()
                 .str.contains("sale", na=False)
                 if "transactionType" in df.columns else None)

    n_purchases = int(purchase_mask.sum()) if purchase_mask is not None else 0
    n_sales = int(sale_mask.sum()) if sale_mask is not None else 0

    st.markdown(
        '<div class="eq-section-label">CONGRESSIONAL TRADES · FINNHUB</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("TOTAL TRADES", str(n_total))
    c2.metric("UNIQUE POLITICIANS", str(n_unique))
    c3.metric("PURCHASES / SALES", f"{n_purchases} / {n_sales}")
    c4.metric("LAST TRADE", last_date)

    # ---- Recent trades table ----
    show = df.head(25).copy()
    if "transactionDate" in show.columns:
        show["transactionDate"] = show["transactionDate"].dt.strftime("%Y-%m-%d")
    if "filingDate" in show.columns:
        show["filingDate"] = show["filingDate"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "—"
        )

    keep_cols = [c for c in (
        "transactionDate", "name", "position", "ownerType",
        "transactionType", "amountFrom", "amountTo", "filingDate",
    ) if c in show.columns]

    if "amountFrom" in show.columns and "amountTo" in show.columns:
        show["amount_range"] = show.apply(
            lambda r: _fmt_range(r.get("amountFrom"), r.get("amountTo")), axis=1
        )
        keep_cols = [c for c in keep_cols
                     if c not in ("amountFrom", "amountTo")] + ["amount_range"]

    show = show[keep_cols].rename(columns={
        "transactionDate":  "Date",
        "name":             "Politician",
        "position":         "Position",
        "ownerType":        "Owner",
        "transactionType":  "Type",
        "amount_range":     "Amount",
        "filingDate":       "Filed",
    })
    st.markdown(
        '<div class="eq-section-label" style="margin-top:12px;">'
        'RECENT TRADES</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption(
        "Amount ranges reflect disclosure brackets — politicians report "
        "trades as buckets, not exact dollar amounts."
    )
