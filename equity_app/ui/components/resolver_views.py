"""
Render the page based on ``ResolverResult.ui_mode``.

The page calls ``maybe_render_non_standard_view(result)`` early. If the
resolver returned a non-standard mode (etf / informational / error /
full_bank / full_reit / full_insurance / partial), this module renders
the right view AND returns True — telling the page to skip the rest of
the standard pipeline.

For ``ui_mode == "full"`` we return False so the existing rich pipeline
runs untouched. For ``"partial"`` we render a disclaimer banner but
return False — the standard pipeline still executes (it's just
yfinance-only and the user is forewarned).

For ``full_bank`` / ``full_reit`` / ``full_insurance`` we render the
sector-specific dashboard ABOVE the standard analysis, then return False
so the rest of the page (Overview / Valuation / etc.) still renders too.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"


# ============================================================
# Format helpers
# ============================================================
def _fmt_pct(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v*100:.2f}%"


def _fmt_x(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.2f}×"


def _fmt_usd(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12: return f"{sign}${av/1e12:,.2f}T"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.0f}M"
    return f"{sign}${av:,.0f}"


# ============================================================
# Warning banner (used by every mode that has warnings)
# ============================================================
def _render_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    items = "".join(
        '<li style="color:var(--text-secondary); font-size:13px; '
        'margin-bottom:4px;">' + w + '</li>'
        for w in warnings
    )
    st.markdown(
        '<div class="eq-card" style="padding:14px 18px; '
        'border-left:3px solid var(--accent); margin-bottom:14px;">'
        '<div class="eq-section-label">CLASSIFICATION NOTES</div>'
        f'<ul style="margin:8px 0 0 18px; padding:0;">{items}</ul></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Error / Informational / ETF
# ============================================================
def _render_error_view(ticker: str, result) -> None:
    msg = (result.warnings[0] if result.warnings
           else f"Ticker {ticker!r} could not be classified.")
    st.markdown(
        '<div class="eq-card" style="padding:32px; text-align:center; '
        f'border:1px solid {_DOWNSIDE}; margin:20px 0;">'
        f'<div style="color:{_DOWNSIDE}; font-size:42px;">⚠</div>'
        f'<div style="color:var(--text-primary); font-size:20px; '
        f'font-weight:500; margin-top:10px;">Cannot analyze {ticker!r}</div>'
        f'<div style="color:var(--text-secondary); font-size:14px; '
        f'margin-top:6px;">{msg}</div>'
        '<div style="color:var(--text-muted); font-size:12px; '
        'margin-top:20px;">Try a US-listed common stock — e.g. AAPL, NVDA, '
        'NFLX, KO, JPM.</div></div>',
        unsafe_allow_html=True,
    )


def _render_informational_view(ticker: str, result) -> None:
    title_map = {
        "crypto":      "Cryptocurrency asset",
        "index":       "Market index",
        "mutual_fund": "Mutual fund",
    }
    title = title_map.get(result.type.value, "Limited analysis available")
    st.markdown(
        '<div class="eq-card" style="padding:24px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">LIMITED ANALYSIS</div>'
        f'<div style="color:var(--text-primary); font-size:20px; '
        f'font-weight:500; margin-top:6px;">{ticker} · {title}</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'line-height:1.5; margin-top:10px;">{result.explanation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_etf_view(ticker: str, result) -> None:
    data = result.etf_data or {}
    name = data.get("name") or ticker
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">ETF · LIMITED EQUITY ANALYSIS</div>'
        f'<div style="color:var(--text-primary); font-size:22px; '
        f'font-weight:500; margin-top:6px;">{name}</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'margin-top:6px;">ETFs hold portfolios of other securities. '
        'No income statement / balance sheet / DCF — but expense ratio, '
        'AUM, holdings + price history all work.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("EXPENSE RATIO",
              _fmt_pct(data.get("expense_ratio"))
              if data.get("expense_ratio") is not None else "—")
    c2.metric("AUM",         _fmt_usd(data.get("aum")))
    c3.metric("YIELD",       _fmt_pct(data.get("yield")))
    c4.metric("CATEGORY",    str(data.get("category") or "—"))

    holdings = data.get("top_holdings") or []
    if holdings:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            'TOP HOLDINGS / PEER ETFs</div>',
            unsafe_allow_html=True,
        )
        rows = [{
            "Asset":      h.get("asset") or "—",
            "Name":       h.get("name") or "—",
            "Weight":     (f"{h['weight_pct']:.2f}%"
                            if h.get("weight_pct") is not None else "—"),
            "Shares":     (f"{h['shares']:,.0f}"
                            if h.get("shares") is not None else "—"),
            "Market val": _fmt_usd(h.get("market_value")),
        } for h in holdings]
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)
    summary = data.get("summary")
    if summary:
        with st.expander("Fund description", expanded=False):
            st.write(summary)
    if data.get("note"):
        st.caption(data["note"])


# ============================================================
# Bank / REIT / Insurance dashboards
# ============================================================
def _render_bank_dashboard(ticker: str, result) -> None:
    data = result.sector_data or {}
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">BANK-SPECIFIC METRICS · SEC EDGAR</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'margin-top:6px;">Standard gross-margin / inventory metrics do not '
        'apply. Below: NIM, efficiency, loan/deposit ratio, ROE/ROA.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if not data.get("available"):
        st.caption(data.get("note") or "Bank metrics unavailable.")
        return

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("NET INTEREST MARGIN", _fmt_pct(data.get("nim")))
    c2.metric("EFFICIENCY RATIO",    _fmt_pct(data.get("efficiency_ratio")))
    c3.metric("LOAN / DEPOSIT",      _fmt_x(data.get("loan_to_deposit")))
    c4.metric("ROE",                  _fmt_pct(data.get("roe")))

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("INTEREST INCOME",   _fmt_usd(data.get("interest_income")))
    c2.metric("INTEREST EXPENSE",  _fmt_usd(data.get("interest_expense")))
    c3.metric("NET INTEREST INC.", _fmt_usd(data.get("net_interest_income")))
    c4.metric("PROVISION FOR LOAN LOSSES",
              _fmt_usd(data.get("provision_for_loan_losses")))

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("TOTAL LOANS",    _fmt_usd(data.get("total_loans")))
    c2.metric("TOTAL DEPOSITS", _fmt_usd(data.get("total_deposits")))
    c3.metric("TOTAL ASSETS",   _fmt_usd(data.get("total_assets")))
    c4.metric("TOTAL EQUITY",   _fmt_usd(data.get("total_equity")))

    if data.get("note"):
        st.caption(data["note"])


def _render_reit_dashboard(ticker: str, result) -> None:
    data = result.sector_data or {}
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">REIT-SPECIFIC METRICS · SEC EDGAR</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'margin-top:6px;">FFO and AFFO replace EPS for REIT analysis. '
        'Standard P/E is misleading; use P/FFO instead.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if not data.get("available"):
        st.caption(data.get("note") or "REIT metrics unavailable.")
        return

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("FFO",   _fmt_usd(data.get("ffo")))
    c2.metric("AFFO",  _fmt_usd(data.get("affo")))
    fps = data.get("ffo_per_share")
    afps = data.get("affo_per_share")
    c3.metric("FFO / SHARE",  f"${fps:.2f}" if fps else "—")
    c4.metric("AFFO / SHARE", f"${afps:.2f}" if afps else "—")

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("RENTAL INCOME",     _fmt_usd(data.get("rental_income")))
    c2.metric("DEPRECIATION",      _fmt_usd(data.get("depreciation")))
    c3.metric("CAPEX",             _fmt_usd(data.get("capex")))
    c4.metric("DIVIDENDS PAID",    _fmt_usd(data.get("dividends_paid")))

    if data.get("note"):
        st.caption(data["note"])


def _render_insurance_dashboard(ticker: str, result) -> None:
    data = result.sector_data or {}
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        'border-left:3px solid var(--accent);">'
        '<div class="eq-section-label">INSURANCE-SPECIFIC METRICS · SEC EDGAR</div>'
        f'<div style="color:var(--text-secondary); font-size:13px; '
        f'margin-top:6px;">Combined ratio &lt; 100% means underwriting profit. '
        'Investment yield captures float deployment.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if not data.get("available"):
        st.caption(data.get("note") or "Insurance metrics unavailable.")
        return

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("COMBINED RATIO",  _fmt_pct(data.get("combined_ratio")))
    c2.metric("INVESTMENT YIELD", _fmt_pct(data.get("investment_yield")))
    c3.metric("ROE",              _fmt_pct(data.get("roe")))
    c4.metric("NET INCOME",       _fmt_usd(data.get("net_income")))

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("PREMIUM REVENUE",      _fmt_usd(data.get("premium_revenue")))
    c2.metric("INVESTMENT INCOME",    _fmt_usd(data.get("investment_income")))
    c3.metric("POLICYHOLDER BENEFITS", _fmt_usd(data.get("policyholder_benefits")))
    c4.metric("UNDERWRITING EXPENSE",  _fmt_usd(data.get("underwriting_expense")))

    if data.get("note"):
        st.caption(data["note"])


# ============================================================
# Public dispatcher
# ============================================================
def maybe_render_non_standard_view(result) -> bool:
    """
    Returns True iff the page should STOP and not run the standard
    pipeline. Returns False when the standard pipeline should still run
    (full / full_bank / full_reit / full_insurance / partial).

    Sector dashboards render here AND return False — so the bank panel
    appears above the regular Overview/Valuation/etc. tabs.
    """
    mode = result.ui_mode
    warnings = list(result.warnings)

    if mode == "error":
        _render_error_view(result.ticker, result)
        return True

    if mode == "informational":
        _render_informational_view(result.ticker, result)
        return True

    if mode == "etf":
        _render_etf_view(result.ticker, result)
        if result.classification and result.classification.exchange:
            st.caption(f"Listed on {result.classification.exchange}.")
        return True

    if mode == "partial":
        _render_warnings(warnings)
        return False     # let the standard pipeline run (yfinance-only)

    if mode == "full_bank":
        _render_warnings(warnings)
        _render_bank_dashboard(result.ticker, result)
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        return False

    if mode == "full_reit":
        _render_warnings(warnings)
        _render_reit_dashboard(result.ticker, result)
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        return False

    if mode == "full_insurance":
        _render_warnings(warnings)
        _render_insurance_dashboard(result.ticker, result)
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        return False

    # mode == "full": no extra UI, run pipeline as-is
    return False
