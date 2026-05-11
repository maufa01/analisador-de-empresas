"""
Financial-statements viewer powered by SEC EDGAR.

Three sub-tabs (Income · Balance · Cash flow) plus a Summary tab. Each
table supports three views via a radio:

    Absolute      raw $ values (shortest scale per cell)
    Common-size   each line as a % of the base line
                    (income → revenue, balance → total_assets;
                     no-op on cashflow)
    YoY growth    period-over-period % change (income only)

Annual / quarterly toggle. Year slider caps the visible columns at
[5, 20]. SEC delivers up to 30+ years of annual statements for many
filers; the slider is a usability cap, not a fetch limit.
"""
from __future__ import annotations
from typing import Optional

import logging
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.financial_statements import (
    INCOME_LINES, BALANCE_LINES, CASHFLOW_LINES,
    StandardisedStatements, get_standardised_statements,
)
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, GAINS,
)

logger = logging.getLogger(__name__)
_DOWNSIDE = "rgba(184,115,51,1)"


def _fmt_value(val, line_key: str, view: str) -> str:
    if val is None or pd.isna(val):
        return "—"
    if view == "Common-size":
        return f"{val:.1f}%"
    if view == "YoY growth":
        return f"{val:+.1f}%"
    # Absolute
    line_l = line_key.lower()
    if "eps" in line_l:
        return f"${val:.2f}"
    if "shares" in line_l:
        if abs(val) >= 1e9:
            return f"{val/1e9:,.2f}B"
        return f"{val/1e6:,.1f}M"
    if abs(val) >= 1e12: return f"${val/1e12:,.2f}T"
    if abs(val) >= 1e9:  return f"${val/1e9:,.2f}B"
    if abs(val) >= 1e6:  return f"${val/1e6:,.1f}M"
    return f"${val:,.0f}"


def _color_for_value(val, view: str) -> str:
    if view == "YoY growth" and isinstance(val, (int, float)) and pd.notna(val):
        if val > 0:  return "var(--gains)"
        if val < 0:  return _DOWNSIDE
    return "var(--text-primary)"


def _cap_to_recent_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    """Deduplica columnas por año fiscal y devuelve los últimos N años
    ordenados ascendente.

    Why: SEC EDGAR + yfinance + FMP combined puede tener múltiples
    period_end dentro del mismo fiscal year. Casos típicos:
    - AAPL FY2008 históricamente aparece 4+ veces por variaciones de
      filing — columnas duplicadas tipo FY 2008 x4.
    - MU FY ends en septiembre y SEC ships 2022-09-01 (10-K real) +
      2022-12-01 / 2023-03-02 / 2023-06-01 como comparative data en
      filings posteriores; esos rows tienen mostly-NaN y antes
      pisaban al 10-K real cuando se hacía `keep="last"` por año.

    Estrategia: para cada año, quedarse con el row que tiene MÁS
    campos no-null (típicamente el 10-K real vs comparative). Empate
    → último por fecha.
    """
    if df is None or df.empty or years <= 0:
        return df
    try:
        cols = pd.to_datetime(df.columns, errors="coerce")
    except (TypeError, ValueError):
        return df.iloc[:, -years:]
    if cols.isna().all():
        return df.iloc[:, -years:]
    order = cols.argsort()
    df_sorted = df.iloc[:, order]
    cols_sorted = cols[order]
    # Non-null count per column. Period is in columns (df is transposed),
    # so .notna().sum(axis=0) counts populated fields per period.
    non_null = df_sorted.notna().sum(axis=0)
    years_idx = pd.Series(cols_sorted.year, index=range(len(cols_sorted)))
    # For each year, keep the column-position with the max non-null
    # count. groupby preserves order so ties resolve to the last one
    # (which is the most recent date — same as old behaviour for
    # well-behaved single-row years like AAPL/MSFT).
    keep_positions = (
        non_null.reset_index(drop=True)
        .groupby(years_idx)
        .idxmax()
        .values
    )
    df_dedup = df_sorted.iloc[:, sorted(keep_positions)]
    return df_dedup.iloc[:, -years:]


def _render_statement_table(
    df: pd.DataFrame, line_specs: list, *, view: str,
) -> None:
    if df is None or df.empty:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'No {view.lower()} data available for this statement.</div>',
            unsafe_allow_html=True,
        )
        return

    line_dict = {k: (label, is_subtotal) for k, label, is_subtotal in line_specs}

    # Header row
    head = (
        '<tr style="background:var(--surface-raised);">'
        '<th style="padding:10px 14px; text-align:left; '
        'color:var(--text-muted); font-size:11px; '
        'letter-spacing:0.6px; text-transform:uppercase; min-width:200px;">'
        'Line item</th>'
    )
    for col in df.columns:
        date_str = (pd.Timestamp(col).strftime("%Y")
                    if isinstance(col, pd.Timestamp) else str(col)[:4])
        head += (
            '<th style="padding:10px 14px; text-align:right; '
            'color:var(--text-muted); font-size:11px; '
            'letter-spacing:0.6px; text-transform:uppercase;">'
            f'{date_str}</th>'
        )
    head += '</tr>'

    body_rows = []
    for line_key in df.index:
        if line_key not in line_dict:
            continue
        label, is_subtotal = line_dict[line_key]
        weight = "500" if is_subtotal else "400"
        bg_style = (
            "background:rgba(201,169,97,0.05);" if is_subtotal else ""
        )
        cells = (
            f'<td style="padding:8px 14px; color:var(--text-primary); '
            f'font-weight:{weight}; font-size:13px;">{label}</td>'
        )
        for col in df.columns:
            val = df.loc[line_key, col]
            color = _color_for_value(val, view) if is_subtotal else _color_for_value(val, view)
            cells += (
                '<td style="padding:8px 14px; text-align:right; '
                f'color:{color}; font-variant-numeric:tabular-nums; '
                f'font-size:13px; font-weight:{weight};">'
                f'{_fmt_value(val, line_key, view)}</td>'
            )
        body_rows.append(f'<tr style="{bg_style}">{cells}</tr>')

    st.markdown(
        '<div class="eq-card" style="padding:0; overflow-x:auto;">'
        '<table style="width:100%; border-collapse:collapse;">'
        '<thead>' + head + '</thead>'
        '<tbody>' + "".join(body_rows) + '</tbody>'
        '</table></div>',
        unsafe_allow_html=True,
    )


def _trend_chart(df: pd.DataFrame, lines: list[str],
                  title: str) -> Optional[go.Figure]:
    """Two-line evolution chart for the headline metrics."""
    fig = go.Figure()
    palette = {lines[0]: ACCENT, lines[1]: GAINS} if len(lines) >= 2 else {}
    plotted = False
    for ln in lines:
        if ln not in df.index:
            continue
        s = df.loc[ln].dropna()
        if s.empty:
            continue
        # Reverse to ascending for charting
        s = s.iloc[::-1]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values / 1e9,
            mode="lines+markers",
            name=ln.replace("_", " ").title(),
            line=dict(color=palette.get(ln, "#9CA3AF"), width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x|%Y}</b><br>$%{y:,.2f}B<extra></extra>",
        ))
        plotted = True
    if not plotted:
        return None
    fig.update_layout(
        title=title,
        height=300, margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, title="USD billions"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def _select_view_df(stmts: StandardisedStatements, statement: str,
                     view: str) -> tuple[pd.DataFrame, str]:
    """Pick the right DataFrame based on the selected view, and an
    effective view label (common-size auto-falls-back on cashflow)."""
    if view == "Common-size":
        if statement == "income":
            return stmts.common_size_income, "Common-size"
        if statement == "balance":
            return stmts.common_size_balance, "Common-size"
        # cashflow: common-size doesn't apply naturally — fall back to absolute
        return stmts.cashflow, "Absolute"
    if view == "YoY growth":
        if statement == "income":
            return stmts.yoy_income, "YoY growth"
        # Compute YoY on the fly for the other statements
        df = getattr(stmts, statement)
        if df is None or df.empty or len(df.columns) < 2:
            return df, "YoY growth"
        asc = df.iloc[:, ::-1]
        pct = asc.pct_change(axis=1) * 100.0
        return pct.iloc[:, ::-1], "YoY growth"
    return getattr(stmts, statement), "Absolute"


def _render_summary(stmts: StandardisedStatements, *, years: int) -> None:
    income = stmts.income
    if income is None or income.empty:
        st.info("No SEC EDGAR data available for this ticker.")
        return

    latest = income.iloc[:, 0]
    prior = income.iloc[:, 1] if income.shape[1] > 1 else None

    revenue = latest.get("revenue")
    op_income = latest.get("operating_income")
    net_income = latest.get("net_income")
    rev_yoy = ((revenue / prior.get("revenue") - 1) * 100
               if prior is not None and prior.get("revenue") else None)

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("REVENUE",
              f"${revenue/1e9:,.2f}B" if revenue else "—",
              f"{rev_yoy:+.1f}%" if rev_yoy is not None else "")
    c2.metric("OPERATING INCOME",
              f"${op_income/1e9:,.2f}B" if op_income else "—")
    c3.metric("NET INCOME",
              f"${net_income/1e9:,.2f}B" if net_income else "—")
    c4.metric("NET MARGIN",
              f"{(net_income/revenue)*100:.1f}%"
              if revenue and net_income is not None else "—")

    # CAGRs
    if "revenue" in income.index:
        rev_series = income.loc["revenue"].iloc[:years]
        cagrs = []
        for n in (5, 10):
            if len(rev_series) > n and rev_series.iloc[n] and rev_series.iloc[n] > 0:
                cagr = (rev_series.iloc[0] / rev_series.iloc[n]) ** (1 / n) - 1
                cagrs.append((n, cagr))
        if cagrs:
            st.markdown(
                '<div class="eq-section-label" style="margin-top:14px;">'
                'REVENUE CAGR</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(len(cagrs), gap="small")
            for col, (n, val) in zip(cols, cagrs):
                col.metric(f"{n}-YEAR", f"{val*100:.2f}%")


# ============================================================
# Public API
# ============================================================
def render_financial_statements_panel(ticker: str) -> None:
    """SEC EDGAR financial-statements viewer with annual / quarterly,
    absolute / common-size / YoY views, and per-statement charts."""
    st.caption(
        "Direct from SEC EDGAR Company Facts (XBRL). Cached on disk; "
        "annual filings often go back to 1993."
    )

    cols = st.columns([1.2, 1.4, 2], gap="small")
    with cols[0]:
        freq_label = st.radio(
            "Frequency", ["Annual", "Quarterly"],
            horizontal=True, label_visibility="collapsed",
            key=f"sec_freq_{ticker}",
        )
        freq = "annual" if freq_label == "Annual" else "quarterly"
    with cols[1]:
        view = st.radio(
            "View", ["Absolute", "Common-size", "YoY growth"],
            horizontal=True, label_visibility="collapsed",
            key=f"sec_view_{ticker}",
        )
    with cols[2]:
        years = st.slider(
            "Years to display",
            min_value=3, max_value=10, value=5,
            help="Default 5y. Bump higher only when you need deeper "
                 "historical context.",
            key=f"sec_years_{ticker}",
        )

    with st.spinner("Loading from SEC EDGAR…"):
        stmts = get_standardised_statements(ticker, freq=freq)

    if stmts is None or stmts.income.empty:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            f'<span class="eq-section-label">FINANCIAL STATEMENTS · {freq.upper()}</span>'
            f'<div style="margin-top:8px;">{stmts.note or "No data available."}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    sub = st.tabs(["Summary", "Income statement", "Balance sheet", "Cash flow"])

    with sub[0]:
        _render_summary(stmts, years=years)

    with sub[1]:
        df, eff_view = _select_view_df(stmts, "income", view)
        df = _cap_to_recent_years(df, years)
        _render_statement_table(df, INCOME_LINES, view=eff_view)
        if eff_view == "Absolute":
            chart_df = _cap_to_recent_years(stmts.income, years)
            fig = _trend_chart(chart_df, ["revenue", "net_income"],
                                "Revenue & Net income")
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})

    with sub[2]:
        df, eff_view = _select_view_df(stmts, "balance", view)
        df = _cap_to_recent_years(df, years)
        _render_statement_table(df, BALANCE_LINES, view=eff_view)
        if eff_view == "Absolute":
            chart_df = _cap_to_recent_years(stmts.balance, years)
            fig = _trend_chart(chart_df,
                                ["total_assets", "stockholders_equity"],
                                "Total assets & Equity")
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})

    with sub[3]:
        df, eff_view = _select_view_df(stmts, "cashflow", view)
        df = _cap_to_recent_years(df, years)
        _render_statement_table(df, CASHFLOW_LINES, view=eff_view)
        if eff_view == "Absolute":
            chart_df = _cap_to_recent_years(stmts.cashflow, years)
            fig = _trend_chart(
                chart_df,
                ["operating_cash_flow", "free_cash_flow"],
                "Operating cash flow & FCF",
            )
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
