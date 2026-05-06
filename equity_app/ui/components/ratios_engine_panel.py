"""
Ratios panel powered by the SEC-driven ``RatioEngine``.

Layout: 8 sub-tabs (Profitability · Liquidity · Leverage · Efficiency
· Valuation · Growth · DuPont · 10y History). Each ratio renders as a
small card with its formula spelled out and, when a sector is known,
the Damodaran benchmark next to the value.

Pure UI — pulls everything from ``RatioEngine``. No network calls.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.ratio_engine import RatioEngine
from data.industry_benchmarks import get_benchmark
from ui.theme import (
    SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT, GAINS,
)

_DOWNSIDE = "rgba(184,115,51,1)"


# ============================================================
# Tiny helpers
# ============================================================
def _fmt_pct(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v*100:.1f}%"


def _fmt_x(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.2f}×"


def _fmt_days(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.0f} days"


def _fmt_usd(v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12: return f"{sign}${av/1e12:,.2f}T"
    if av >= 1e9:  return f"{sign}${av/1e9:,.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:,.0f}M"
    return f"{sign}${av:,.0f}"


def _color_pct(label: str, value: Optional[float]) -> str:
    if value is None:
        return "var(--text-muted)"
    label_l = label.lower()
    if any(k in label_l for k in ("margin", "roe", "roa", "roic", "roce", "yield")):
        if value > 0.20: return "var(--gains)"
        if value > 0.10: return "var(--accent)"
        if value > 0:    return "var(--text-secondary)"
        return _DOWNSIDE
    return "var(--text-primary)"


def _color_ratio(label: str, value: Optional[float]) -> str:
    if value is None:
        return "var(--text-muted)"
    label_l = label.lower()
    if "current" in label_l or "quick" in label_l or "cash ratio" in label_l:
        if value > 2: return "var(--gains)"
        if value > 1: return "var(--accent)"
        return _DOWNSIDE
    if "debt" in label_l:
        if value < 0.5: return "var(--gains)"
        if value < 1.0: return "var(--accent)"
        return _DOWNSIDE
    if "interest" in label_l or "coverage" in label_l:
        if value > 5: return "var(--gains)"
        if value > 2: return "var(--accent)"
        return _DOWNSIDE
    return "var(--text-primary)"


def _bench_strip(label: str, value: Optional[float],
                  benchmark: Optional[float], *,
                  pct: bool) -> str:
    """Returns the inline 'Sector avg X (±N%)' html string."""
    if benchmark is None or value is None:
        return ""
    if benchmark == 0:
        diff_pct = 0.0
    else:
        diff_pct = ((value - benchmark) / abs(benchmark)) * 100.0
    arrow = "▲" if diff_pct > 0 else "▼" if diff_pct < 0 else "·"
    color = ("var(--gains)" if diff_pct > 0 else
             _DOWNSIDE if diff_pct < 0 else "var(--text-muted)")
    bench_str = (f"{benchmark*100:.1f}%" if pct else f"{benchmark:.2f}×")
    return (
        '<div style="color:var(--text-muted); font-size:11px; '
        f'margin-top:4px;">Sector avg {bench_str} '
        f'<span style="color:{color};">{arrow} {abs(diff_pct):.0f}%</span>'
        '</div>'
    )


def _render_ratio_card(
    *,
    label: str,
    value: Optional[float],
    fmt: str,
    formula: Optional[str] = None,
    benchmark: Optional[float] = None,
) -> None:
    if fmt == "pct":
        formatted = _fmt_pct(value)
        color = _color_pct(label, value)
        bench_html = _bench_strip(label, value, benchmark, pct=True)
    elif fmt == "x":
        formatted = _fmt_x(value)
        color = _color_ratio(label, value)
        bench_html = _bench_strip(label, value, benchmark, pct=False)
    elif fmt == "days":
        formatted = _fmt_days(value)
        color = "var(--text-primary)"
        bench_html = ""
    elif fmt == "usd":
        formatted = _fmt_usd(value)
        color = "var(--text-primary)"
        bench_html = ""
    else:
        formatted = "—" if value is None else f"{value:.2f}"
        color = "var(--text-primary)"
        bench_html = ""

    formula_html = (
        f'<div style="color:var(--text-muted); font-size:10px; '
        f'font-family:monospace; margin-top:6px;">{formula}</div>'
        if formula else ""
    )

    st.markdown(
        '<div class="eq-card" style="padding:14px 16px;">'
        f'<div class="eq-idx-label">{label}</div>'
        f'<div style="color:{color}; font-size:24px; font-weight:500; '
        f'letter-spacing:-0.4px; font-variant-numeric:tabular-nums; '
        f'margin-top:4px;">{formatted}</div>'
        + bench_html
        + formula_html
        + '</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Sub-tab renderers
# ============================================================
def _render_profitability(engine: RatioEngine, ratios: dict,
                           sector: Optional[str]) -> None:
    st.markdown('<div class="eq-section-label">PROFITABILITY</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="GROSS MARGIN", value=ratios.get("gross_margin"),
                           fmt="pct", formula="Gross profit / Revenue",
                           benchmark=get_benchmark(sector, "gross_margin"))
    with c2:
        _render_ratio_card(label="OPERATING MARGIN", value=ratios.get("operating_margin"),
                           fmt="pct", formula="Operating income / Revenue",
                           benchmark=get_benchmark(sector, "operating_margin"))
    with c3:
        _render_ratio_card(label="NET MARGIN", value=ratios.get("net_margin"),
                           fmt="pct", formula="Net income / Revenue",
                           benchmark=get_benchmark(sector, "net_margin"))
    with c4:
        _render_ratio_card(label="FCF MARGIN", value=ratios.get("fcf_margin"),
                           fmt="pct", formula="Free cash flow / Revenue",
                           benchmark=get_benchmark(sector, "fcf_margin"))

    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="ROE", value=ratios.get("roe"),
                           fmt="pct", formula="NI / Avg equity",
                           benchmark=get_benchmark(sector, "roe"))
    with c2:
        _render_ratio_card(label="ROA", value=ratios.get("roa"),
                           fmt="pct", formula="NI / Avg total assets",
                           benchmark=get_benchmark(sector, "roa"))
    with c3:
        _render_ratio_card(label="ROIC", value=ratios.get("roic"),
                           fmt="pct", formula="NOPAT / Invested capital",
                           benchmark=get_benchmark(sector, "roic"))
    with c4:
        _render_ratio_card(label="ROCE", value=ratios.get("roce"),
                           fmt="pct", formula="EBIT / (Assets − Curr. liab.)",
                           benchmark=get_benchmark(sector, "roce"))


def _render_liquidity(engine: RatioEngine, ratios: dict,
                       sector: Optional[str]) -> None:
    st.markdown('<div class="eq-section-label">LIQUIDITY</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="CURRENT RATIO", value=ratios.get("current_ratio"),
                           fmt="x", formula="Current assets / Current liab.",
                           benchmark=get_benchmark(sector, "current_ratio"))
    with c2:
        _render_ratio_card(label="QUICK RATIO", value=ratios.get("quick_ratio"),
                           fmt="x",
                           formula="(Current assets − Inventory) / Current liab.",
                           benchmark=get_benchmark(sector, "quick_ratio"))
    with c3:
        _render_ratio_card(label="CASH RATIO", value=ratios.get("cash_ratio"),
                           fmt="x",
                           formula="(Cash + ST inv.) / Current liab.")
    with c4:
        _render_ratio_card(label="WORKING CAPITAL",
                           value=ratios.get("working_capital"),
                           fmt="usd",
                           formula="Current assets − Current liab.")


def _render_leverage(engine: RatioEngine, ratios: dict,
                      sector: Optional[str]) -> None:
    st.markdown('<div class="eq-section-label">LEVERAGE</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="DEBT / EQUITY",
                           value=ratios.get("debt_to_equity"),
                           fmt="x", formula="Total debt / Equity",
                           benchmark=get_benchmark(sector, "debt_to_equity"))
    with c2:
        _render_ratio_card(label="DEBT / ASSETS",
                           value=ratios.get("debt_to_assets"),
                           fmt="x", formula="Total debt / Total assets",
                           benchmark=get_benchmark(sector, "debt_to_assets"))
    with c3:
        _render_ratio_card(label="DEBT / EBITDA",
                           value=ratios.get("debt_to_ebitda"),
                           fmt="x", formula="Total debt / EBITDA")
    with c4:
        _render_ratio_card(label="INTEREST COVERAGE",
                           value=ratios.get("interest_coverage"),
                           fmt="x", formula="EBIT / |Interest expense|",
                           benchmark=get_benchmark(sector, "interest_coverage"))

    c1, _, _, _ = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="EQUITY RATIO",
                           value=ratios.get("equity_ratio"),
                           fmt="pct", formula="Equity / Total assets")


def _render_efficiency(engine: RatioEngine, ratios: dict,
                        sector: Optional[str]) -> None:
    st.markdown('<div class="eq-section-label">EFFICIENCY</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="ASSET TURNOVER",
                           value=ratios.get("asset_turnover"),
                           fmt="x", formula="Revenue / Avg total assets",
                           benchmark=get_benchmark(sector, "asset_turnover"))
    with c2:
        _render_ratio_card(label="INVENTORY TURNOVER",
                           value=ratios.get("inventory_turnover"),
                           fmt="x", formula="COGS / Avg inventory")
    with c3:
        _render_ratio_card(label="DSO",
                           value=ratios.get("days_sales_outstanding"),
                           fmt="days", formula="(Avg AR / Revenue) × 365")
    with c4:
        _render_ratio_card(label="DIO",
                           value=ratios.get("days_inventory"),
                           fmt="days", formula="365 / Inventory turnover")

    c1, c2, _, _ = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="DPO",
                           value=ratios.get("days_payables"),
                           fmt="days", formula="(Avg AP / COGS) × 365")
    with c2:
        _render_ratio_card(label="CASH CONVERSION CYCLE",
                           value=ratios.get("cash_conversion_cycle"),
                           fmt="days", formula="DSO + DIO − DPO")


def _render_valuation(engine: RatioEngine, ratios: dict,
                       sector: Optional[str]) -> None:
    st.markdown('<div class="eq-section-label">VALUATION (LIVE MARKET DATA)</div>',
                unsafe_allow_html=True)
    if engine.market_cap is None and engine.current_price is None:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            'Market cap and current price unavailable — valuation '
            'multiples cannot be computed. (Quote provider may be down.)'
            '</div>',
            unsafe_allow_html=True,
        )
        return
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="P / E (TTM)", value=ratios.get("pe_ratio"),
                           fmt="x", formula="Price / TTM EPS",
                           benchmark=get_benchmark(sector, "pe_ratio"))
    with c2:
        _render_ratio_card(label="P / B", value=ratios.get("pb_ratio"),
                           fmt="x", formula="Market cap / Book equity",
                           benchmark=get_benchmark(sector, "pb_ratio"))
    with c3:
        _render_ratio_card(label="P / S (TTM)", value=ratios.get("ps_ratio"),
                           fmt="x", formula="Market cap / TTM revenue",
                           benchmark=get_benchmark(sector, "ps_ratio"))
    with c4:
        _render_ratio_card(label="EV / EBITDA", value=ratios.get("ev_to_ebitda"),
                           fmt="x", formula="(Mcap + Debt − Cash) / EBITDA",
                           benchmark=get_benchmark(sector, "ev_to_ebitda"))

    c1, c2, c3, _ = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="EV / REVENUE",
                           value=ratios.get("ev_to_revenue"),
                           fmt="x", formula="EV / TTM revenue",
                           benchmark=get_benchmark(sector, "ev_to_revenue"))
    with c2:
        _render_ratio_card(label="FCF YIELD", value=ratios.get("fcf_yield"),
                           fmt="pct", formula="TTM FCF / Market cap",
                           benchmark=get_benchmark(sector, "fcf_yield"))
    with c3:
        _render_ratio_card(label="EARNINGS YIELD",
                           value=ratios.get("earnings_yield"),
                           fmt="pct", formula="1 / P/E (TTM)")


def _render_growth(engine: RatioEngine, ratios: dict) -> None:
    st.markdown('<div class="eq-section-label">GROWTH (CAGR)</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="REVENUE CAGR (5Y)",
                           value=ratios.get("revenue_cagr_5y"),
                           fmt="pct")
    with c2:
        _render_ratio_card(label="REVENUE CAGR (10Y)",
                           value=ratios.get("revenue_cagr_10y"),
                           fmt="pct")
    with c3:
        _render_ratio_card(label="EPS CAGR (5Y)",
                           value=ratios.get("eps_cagr_5y"),
                           fmt="pct")
    with c4:
        _render_ratio_card(label="FCF CAGR (5Y)",
                           value=ratios.get("fcf_cagr_5y"),
                           fmt="pct")
    c1, _, _, _ = st.columns(4, gap="small")
    with c1:
        _render_ratio_card(label="NET INCOME CAGR (5Y)",
                           value=ratios.get("net_income_cagr_5y"),
                           fmt="pct")


def _render_dupont(engine: RatioEngine, ratios: dict) -> None:
    dupont = ratios.get("dupont", {}) or {}
    nm = dupont.get("net_margin")
    at = dupont.get("asset_turnover")
    em = dupont.get("equity_multiplier")
    roe = dupont.get("roe_reported")

    st.markdown('<div class="eq-section-label">DUPONT DECOMPOSITION</div>',
                unsafe_allow_html=True)
    if any(v is None for v in (nm, at, em, roe)):
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            'Insufficient data to decompose ROE this period.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div class="eq-card" style="padding:22px 24px;">'
        '<div style="display:grid; '
        'grid-template-columns:1fr auto 1fr auto 1fr auto 1fr; gap:14px; '
        'align-items:center; text-align:center;">'
        # net margin
        '<div>'
        '<div class="eq-idx-label">NET MARGIN</div>'
        f'<div style="color:var(--text-primary); font-size:22px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'margin-top:6px;">{nm*100:.1f}%</div>'
        '<div style="color:var(--text-muted); font-size:11px;">Profitability</div>'
        '</div>'
        '<div style="color:var(--accent); font-size:22px;">×</div>'
        # asset turnover
        '<div>'
        '<div class="eq-idx-label">ASSET TURNOVER</div>'
        f'<div style="color:var(--text-primary); font-size:22px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'margin-top:6px;">{at:.2f}×</div>'
        '<div style="color:var(--text-muted); font-size:11px;">Efficiency</div>'
        '</div>'
        '<div style="color:var(--accent); font-size:22px;">×</div>'
        # equity multiplier
        '<div>'
        '<div class="eq-idx-label">EQUITY MULTIPLIER</div>'
        f'<div style="color:var(--text-primary); font-size:22px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'margin-top:6px;">{em:.2f}×</div>'
        '<div style="color:var(--text-muted); font-size:11px;">Leverage</div>'
        '</div>'
        '<div style="color:var(--accent); font-size:22px;">=</div>'
        # ROE
        f'<div style="background:rgba(201,169,97,0.10); padding:14px; '
        f'border-radius:8px;">'
        '<div class="eq-idx-label" style="color:var(--accent);">ROE</div>'
        f'<div style="color:var(--accent); font-size:26px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; '
        f'margin-top:6px;">{roe*100:.1f}%</div>'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # Auto-insights — short, opinionated.
    bullets: list[str] = []
    if nm > 0.20:
        bullets.append("High profitability — pricing power or differentiation.")
    elif nm < 0.05:
        bullets.append("Thin margins — commoditised business or cost pressure.")
    if at > 2:
        bullets.append("High asset efficiency — turning the balance sheet hard.")
    elif at < 0.4:
        bullets.append("Capital-intensive business — slow asset turnover.")
    if em > 3:
        bullets.append("⚠ ROE leveraged — equity multiplier > 3, watch refinancing.")
    elif em < 1.5:
        bullets.append("Conservative balance sheet — low leverage.")

    if bullets:
        items = "".join(
            '<li style="color:var(--text-secondary); font-size:13px; '
            'margin-bottom:6px;">'
            + b + '</li>' for b in bullets
        )
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; margin-top:10px;">'
            '<div class="eq-section-label">INSIGHTS</div>'
            f'<ul style="margin:8px 0 0 18px; padding:0;">{items}</ul></div>',
            unsafe_allow_html=True,
        )


def _render_history(engine: RatioEngine) -> None:
    st.markdown('<div class="eq-section-label">10-YEAR HISTORICAL RATIOS</div>',
                unsafe_allow_html=True)
    historical = engine.compute_historical()
    if historical.empty:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px;">'
            'Historical ratios unavailable (no SEC EDGAR data for this ticker).</div>',
            unsafe_allow_html=True,
        )
        return

    available = list(historical.columns)
    default_pick = [r for r in ("roe", "roic", "operating_margin")
                    if r in available]
    selected = st.multiselect(
        "Ratios to plot",
        available,
        default=default_pick or available[:3],
        key=f"hist_ratios_{engine.ticker}",
    )
    if not selected:
        return

    palette = [ACCENT, GAINS, "#9CA3AF", "#B87333", "#6B7280"]
    fig = go.Figure()
    for i, ratio in enumerate(selected):
        s = historical[ratio].dropna() * 100
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            mode="lines+markers",
            name=ratio.replace("_", " ").title(),
            line=dict(color=palette[i % len(palette)], width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x|%Y}</b><br>%{y:.2f}%<extra></extra>",
        ))
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, family="Inter, sans-serif", size=11),
        xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER, ticksuffix="%"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})

    # Compact table
    table = (historical[selected] * 100).round(2)
    table.index = [pd.Timestamp(i).strftime("%Y") for i in table.index]
    st.dataframe(table.head(15), use_container_width=True)


# ============================================================
# Public API
# ============================================================
def render_ratios_engine_panel(
    ticker: str, *,
    market_cap: Optional[float] = None,
    current_price: Optional[float] = None,
    sector: Optional[str] = None,
) -> None:
    """8-sub-tab Ratios panel powered by ``RatioEngine``."""
    engine = RatioEngine(ticker, market_cap=market_cap,
                         current_price=current_price)

    if not engine.has_data:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:13px;">'
            '<span class="eq-section-label">RATIOS · ENGINE</span>'
            f'<div style="margin-top:8px;">{engine.note or "No SEC EDGAR data for this ticker."}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    st.caption(
        "Every ratio computed from SEC EDGAR statements (cached). "
        "Sector benchmarks via Damodaran. Formulas shown under each card."
    )
    ratios = engine.compute_all()

    tabs = st.tabs([
        "Profitability", "Liquidity", "Leverage", "Efficiency",
        "Valuation", "Growth", "DuPont", "10y History",
    ])
    with tabs[0]: _render_profitability(engine, ratios, sector)
    with tabs[1]: _render_liquidity(engine, ratios, sector)
    with tabs[2]: _render_leverage(engine, ratios, sector)
    with tabs[3]: _render_efficiency(engine, ratios, sector)
    with tabs[4]: _render_valuation(engine, ratios, sector)
    with tabs[5]: _render_growth(engine, ratios)
    with tabs[6]: _render_dupont(engine, ratios)
    with tabs[7]: _render_history(engine)
