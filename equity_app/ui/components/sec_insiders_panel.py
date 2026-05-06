"""
SEC Form 4 insider panel — two-tier UX.

NIVEL 1 (always rendered, 1 SEC request):
    Quick summary of the filings index — total count, last filing,
    last-30-day count, plus a metadata-only table of recent filings.

NIVEL 2 (gated behind an explicit button click, ~50 SEC requests):
    Parse every Form 4 XML, extract every transaction, run cluster +
    CEO / CFO segregation. Cached on disk for 7 days.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.edgar_provider import (
    get_insider_filings_summary,
    fetch_full_insider_history_cached,
    FORM4_TRANSACTION_CODES,
)
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, GAINS,
)


_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_usd(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.1f}M"
    if av >= 1e3:  return f"{sign}${av/1e3:,.0f}K"
    return f"{sign}${av:,.0f}"


def _fmt_signed_usd(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else "+"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.1f}M"
    if av >= 1e3:  return f"{sign}${av/1e3:,.0f}K"
    return f"{sign}${av:,.0f}"


# ============================================================
# Quick (Level-1) view — always shown
# ============================================================
def _render_quick_summary(ticker: str, summary: dict) -> None:
    st.markdown(
        '<div class="eq-section-label">SEC FORM 4 · QUICK INDEX</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("FORM 4 FILINGS (24m)", str(summary["total_filings"]))
    c2.metric("LAST 30 DAYS", str(summary["last_30d_count"]))
    c3.metric("LAST FILING",
              summary["last_filing_date"] or "—")
    c4.metric("DATA SOURCE", "SEC EDGAR")

    filings_list = summary["filings_list"]
    if filings_list is not None and not filings_list.empty:
        with st.expander("Recent filings (metadata only — XML not yet parsed)",
                         expanded=False):
            df = filings_list.head(20).copy()
            keep = [c for c in ("filing_date", "report_date",
                                 "accession_number", "primary_document")
                    if c in df.columns]
            df = df[keep]
            if "filing_date" in df.columns:
                df["filing_date"] = df["filing_date"].dt.strftime("%Y-%m-%d")
            if "report_date" in df.columns:
                df["report_date"] = df["report_date"].apply(
                    lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "—"
                )
            df = df.rename(columns={
                "filing_date":      "Filed",
                "report_date":      "Period",
                "accession_number": "Accession",
                "primary_document": "Document",
            })
            st.dataframe(df, hide_index=True, use_container_width=True)


# ============================================================
# Detailed (Level-2) analytics — only after the user clicks
# ============================================================
def _classify_transactions(df: pd.DataFrame) -> dict:
    """Light analysis — runs on the parsed XML rows."""
    if df.empty:
        return {"net_value": 0.0, "buys": 0, "sells": 0,
                "ceo_net": 0.0, "cfo_net": 0.0, "clusters": []}

    code_col = df["transaction_code"].astype(str)
    buys = df[code_col == "P"]
    sells = df[code_col == "S"]
    bv = float(buys["value"].sum()) if "value" in buys.columns else 0.0
    sv = float(sells["value"].sum()) if "value" in sells.columns else 0.0

    rel = df["relationship"].astype(str).str.lower()
    ceo_mask = rel.str.contains("ceo|chief executive|president", regex=True)
    cfo_mask = rel.str.contains("cfo|chief financial", regex=True)

    def _net(sub: pd.DataFrame) -> float:
        if sub.empty:
            return 0.0
        sub_codes = sub["transaction_code"].astype(str)
        b = sub[sub_codes == "P"]["value"].sum() if "value" in sub.columns else 0.0
        s = sub[sub_codes == "S"]["value"].sum() if "value" in sub.columns else 0.0
        return float(b - s)

    # Cluster detection — 3+ insiders within 30d
    clusters: list[dict] = []
    if not buys.empty and "transaction_date" in buys.columns:
        b = buys.dropna(subset=["transaction_date"]).sort_values("transaction_date")
        last_end: Optional[pd.Timestamp] = None
        for _, row in b.iterrows():
            start = pd.Timestamp(row["transaction_date"])
            if last_end is not None and start <= last_end:
                continue
            end = start + pd.Timedelta(days=30)
            window = b[(b["transaction_date"] >= start)
                       & (b["transaction_date"] <= end)]
            uniq = window["owner"].dropna().unique()
            if len(uniq) >= 3:
                clusters.append({
                    "start_date": start, "end_date": end,
                    "n_insiders": int(len(uniq)),
                    "total_value": float(window["value"].sum()) if "value" in window.columns else 0.0,
                    "names": list(map(str, uniq))[:8],
                })
                last_end = end

    return {
        "net_value": bv - sv,
        "buys":  int(len(buys)),
        "sells": int(len(sells)),
        "ceo_net": _net(df[ceo_mask]),
        "cfo_net": _net(df[cfo_mask]),
        "clusters": clusters,
    }


def _render_full_analysis(ticker: str, df: pd.DataFrame) -> None:
    if df.empty:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            'No transactions parsed from the available filings.</div>',
            unsafe_allow_html=True,
        )
        return

    cls = _classify_transactions(df)
    color = ("var(--gains)" if cls["net_value"] > 0
             else _DOWNSIDE if cls["net_value"] < 0 else "var(--text-muted)")

    # ---- Header card ----
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        f'border-left:4px solid {color}; margin-top:14px;">'
        '<div class="eq-section-label">FULL FORM 4 ANALYSIS · 24M</div>'
        '<div style="display:flex; align-items:baseline; gap:18px; '
        'flex-wrap:wrap; margin-top:6px;">'
        f'<span style="font-size:30px; font-weight:500; letter-spacing:-0.5px; '
        f'color:{color}; font-variant-numeric:tabular-nums;">'
        f'{_fmt_signed_usd(cls["net_value"])}</span>'
        f'<span style="color:var(--text-muted); font-size:12px;">'
        f'NET ACTIVITY · {cls["buys"]} buys · {cls["sells"]} sells</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Exec activity ----
    e1, e2 = st.columns(2, gap="small")
    for col, label, val in (
        (e1, "CEO NET", cls["ceo_net"]),
        (e2, "CFO NET", cls["cfo_net"]),
    ):
        c = ("var(--gains)" if val > 0
             else _DOWNSIDE if val < 0 else "var(--text-muted)")
        with col:
            st.markdown(
                '<div class="eq-card" style="padding:14px 16px;">'
                f'<div class="eq-idx-label">{label}</div>'
                f'<div style="color:{c}; font-size:22px; font-weight:500; '
                f'font-variant-numeric:tabular-nums; margin-top:6px;">'
                f'{_fmt_signed_usd(val)}</div></div>',
                unsafe_allow_html=True,
            )

    # ---- Cluster events ----
    if cls["clusters"]:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'CLUSTER BUYING EVENTS</div>',
            unsafe_allow_html=True,
        )
        for c in cls["clusters"][:6]:
            names_str = ", ".join(c["names"][:5])
            if len(c["names"]) > 5:
                names_str += " …"
            st.markdown(
                '<div class="eq-card" style="padding:12px 16px; '
                'border-left:3px solid var(--accent); margin-top:6px;">'
                '<div style="display:flex; justify-content:space-between; '
                'align-items:baseline;">'
                f'<div><strong style="color:var(--text-primary);">'
                f'{c["start_date"].strftime("%b %Y")}</strong>'
                '<span style="color:var(--text-muted); margin-left:10px;">'
                f'{c["n_insiders"]} insiders</span></div>'
                f'<div style="color:var(--accent); font-weight:500; '
                f'font-variant-numeric:tabular-nums;">'
                f'{_fmt_usd(c["total_value"])}</div></div>'
                f'<div style="color:var(--text-muted); font-size:11px; '
                f'margin-top:6px;">{names_str}</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    # ---- Activity chart ----
    chart_df = df.dropna(subset=["transaction_date", "value"]).copy()
    if not chart_df.empty:
        chart_df["month"] = chart_df["transaction_date"].dt.to_period("M").dt.to_timestamp()
        chart_df["is_buy"] = chart_df["transaction_code"].astype(str) == "P"
        chart_df["is_sell"] = chart_df["transaction_code"].astype(str) == "S"
        grouped = chart_df.groupby("month").apply(
            lambda g: pd.Series({
                "buys":  g.loc[g["is_buy"], "value"].sum(),
                "sells": g.loc[g["is_sell"], "value"].sum(),
            })
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=grouped["month"], y=grouped["buys"] / 1e6,
            name="Buys", marker_color=GAINS,
            hovertemplate="<b>%{x|%b %Y}</b><br>Buys $%{y:.2f}M<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            x=grouped["month"], y=-grouped["sells"] / 1e6,
            name="Sells", marker_color=_DOWNSIDE,
            hovertemplate="<b>%{x|%b %Y}</b><br>Sells $%{y:.2f}M<extra></extra>",
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=0, t=20, b=0),
            paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
            font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
            barmode="relative",
            xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
            yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, ticksuffix="M",
                       title="USD"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
            hovermode="x unified",
        )
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'MONTHLY ACTIVITY</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    # ---- Last 25 transactions table ----
    show = df.head(25).copy()
    if "transaction_date" in show.columns:
        show["transaction_date"] = show["transaction_date"].dt.strftime("%Y-%m-%d")
    if "value" in show.columns:
        show["value"] = show["value"].apply(_fmt_usd)
    if "shares" in show.columns:
        show["shares"] = show["shares"].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
        )
    if "price" in show.columns:
        show["price"] = show["price"].apply(
            lambda x: f"${x:.2f}" if pd.notna(x) else "—"
        )
    if "transaction_code" in show.columns:
        show["transaction_code"] = show["transaction_code"].astype(str).map(
            lambda c: f"{c} · {FORM4_TRANSACTION_CODES.get(c, '')}".strip(" ·")
        )

    keep = [c for c in ("transaction_date", "owner", "relationship",
                         "transaction_code", "shares", "price", "value")
            if c in show.columns]
    show = show[keep].rename(columns={
        "transaction_date":  "Date",
        "owner":             "Insider",
        "relationship":      "Role",
        "transaction_code":  "Code",
        "shares":            "Shares",
        "price":             "Price",
        "value":             "Value",
    })
    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'LAST 25 TRANSACTIONS</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(show, hide_index=True, use_container_width=True)


# ============================================================
# Public entry point
# ============================================================
def render_sec_insiders_panel(ticker: str) -> None:
    """Two-tier UI: quick summary always; full analysis behind a button."""
    with st.spinner("Loading SEC Form 4 filings index…"):
        try:
            summary = get_insider_filings_summary(ticker, months=24)
        except Exception as e:
            st.markdown(
                '<div class="eq-card" style="padding:18px; '
                'color:var(--text-muted); font-size:13px;">'
                '<span class="eq-section-label">SEC FORM 4</span>'
                f'<div style="margin-top:8px;">SEC EDGAR request failed: {e}</div></div>',
                unsafe_allow_html=True,
            )
            return

    if summary["total_filings"] == 0:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            'No Form 4 filings in the last 24 months.</div>',
            unsafe_allow_html=True,
        )
        return

    _render_quick_summary(ticker, summary)

    # ---- UI gate ----
    state_key = f"_sec_form4_loaded_{ticker}"
    n_to_parse = min(summary["total_filings"], 50)

    if st.session_state.get(state_key) is True:
        with st.spinner(f"Parsing {n_to_parse} Form 4 filings… (cached for 7 days after first run)"):
            df = fetch_full_insider_history_cached(
                ticker, months=24, max_filings=50,
            )
        _render_full_analysis(ticker, df)
        if st.button("Refresh full history (re-parse)",
                     key=f"refresh_form4_{ticker}",
                     help=("Drops the 7-day cache for this ticker and "
                           "re-downloads every Form 4 XML.")):
            try:
                from data.cache import cache_clear
                cache_clear("sec_form4_full")
            except Exception:
                pass
            st.session_state[state_key] = False
            st.rerun()
        return

    # Gate
    st.markdown(
        '<div class="eq-card" style="padding:20px 22px; margin-top:14px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">FULL FORM 4 ANALYSIS</div>'
        '<div style="color:var(--text-secondary); font-size:13px; '
        'margin-top:8px; line-height:1.5;">'
        f'Parses every Form 4 XML for the last 24 months '
        f'(<strong style="color:var(--text-primary);">{n_to_parse}</strong> '
        'filings). Includes per-transaction price + share counts, '
        'CEO / CFO segregation, cluster-buying detection, monthly chart.'
        '</div>'
        '<div style="color:var(--text-muted); font-size:11px; margin-top:10px;">'
        '⚠ Heavy operation — ~2 SEC requests per filing. '
        'Takes 1–3 min. Result cached for 7 days.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.button("Load full insider history",
                 type="primary",
                 key=f"load_form4_{ticker}",
                 use_container_width=False):
        st.session_state[state_key] = True
        st.rerun()
