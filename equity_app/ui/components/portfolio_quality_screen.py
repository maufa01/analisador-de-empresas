"""Portfolio quality screen — weighted-avg fundamentals + per-holding flags."""
from __future__ import annotations
from typing import Any, Optional

import math
import pandas as pd
import streamlit as st

from analysis.ratios import _get, free_cash_flow, cagr


# S&P 500 median benchmarks (loose, for the SPY-comparison chips).
_SPY_BENCH = {
    "roic":            0.12,   # 12%
    "fcf_margin":      0.12,
    "net_debt_ebitda": 1.5,    # ratio
    "rev_cagr_5y":     0.08,
}


def _ratio_color(value: Optional[float], bench: float, *, higher_better: bool) -> str:
    if value is None or not math.isfinite(value):
        return "var(--text-muted)"
    if higher_better:
        return "var(--gains)" if value >= bench else "rgba(184,115,51,1)"
    return "var(--gains)" if value <= bench else "rgba(184,115,51,1)"


def _last_finite(s: Optional[pd.Series]) -> Optional[float]:
    if s is None:
        return None
    s = s.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if math.isfinite(v) else None


def _ticker_metrics(bundle) -> dict[str, Optional[float]]:
    """Compute one-row fundamentals for a holding's bundle."""
    if bundle is None:
        return {"roic": None, "fcf_margin": None,
                "net_debt_ebitda": None, "rev_cagr_5y": None,
                "ttm_fcf": None}
    inc = getattr(bundle, "income", None)
    bal = getattr(bundle, "balance", None)
    cf = getattr(bundle, "cash", None)
    if inc is None or inc.empty:
        return {"roic": None, "fcf_margin": None,
                "net_debt_ebitda": None, "rev_cagr_5y": None,
                "ttm_fcf": None}

    rev = _get(inc, "revenue")
    rev_last = _last_finite(rev)

    # ROIC via analysis.ratios.roic (handles avg invested capital)
    try:
        from analysis.ratios import roic as _roic_fn
        roic_s = _roic_fn(inc, bal)
    except Exception:
        roic_s = None
    roic_last = _last_finite(roic_s)

    fcf = free_cash_flow(cf)
    fcf_last = _last_finite(fcf)
    fcf_margin = (fcf_last / rev_last) if (fcf_last and rev_last and rev_last > 0) else None

    # Net debt / EBITDA — derive debt from longTermDebt + ST + current
    debt_proxy = 0.0
    debt_found = False
    if bal is not None and not bal.empty:
        for col in ("totalDebt", "longTermDebt", "shortTermDebt",
                    "currentPortionOfLongTermDebt"):
            if col in bal.columns:
                v = bal[col].iloc[-1]
                if pd.notna(v):
                    debt_proxy += float(v)
                    debt_found = True
                    if col == "totalDebt":
                        break
    cash_eq = None
    if bal is not None and "cashAndCashEquivalents" in bal.columns:
        v = bal["cashAndCashEquivalents"].iloc[-1]
        cash_eq = float(v) if pd.notna(v) else None
    net_debt = (debt_proxy - (cash_eq or 0.0)) if debt_found else None
    ebitda = _get(inc, "ebitda")
    ebitda_last = _last_finite(ebitda)
    nd_ebitda = (net_debt / ebitda_last) if (net_debt is not None and ebitda_last and ebitda_last > 0) else None

    # Revenue 5y CAGR
    rev_cagr = None
    if rev is not None and len(rev.dropna()) >= 2:
        s = rev.dropna()
        if s.iloc[0] > 0:
            g = cagr(s, periods=min(5, len(s) - 1))
            if math.isfinite(g):
                rev_cagr = float(g)

    return {
        "roic":            roic_last,
        "fcf_margin":      fcf_margin,
        "net_debt_ebitda": nd_ebitda,
        "rev_cagr_5y":     rev_cagr,
        "ttm_fcf":         fcf_last,
    }


def render_quality_screen(
    bundles: dict[str, Any],
    weights: dict[str, float],
) -> None:
    if not bundles or not weights:
        st.info("Quality screen needs holdings + bundles.")
        return

    # Normalise weights
    total_w = sum(weights.values())
    if total_w <= 0:
        st.info("Weights sum to zero.")
        return
    norm = {t: w / total_w for t, w in weights.items()}

    per_ticker: dict[str, dict] = {}
    for tkr, w in norm.items():
        b = bundles.get(tkr)
        m = _ticker_metrics(b)
        m["weight"] = w
        per_ticker[tkr] = m

    # Weighted averages — skip tickers with None for that metric, renormalise.
    def _wavg(key: str) -> Optional[float]:
        num, denom = 0.0, 0.0
        for m in per_ticker.values():
            v = m.get(key)
            if v is None or not math.isfinite(v):
                continue
            num += float(v) * m["weight"]
            denom += m["weight"]
        return num / denom if denom > 0 else None

    w_roic = _wavg("roic")
    w_fcfm = _wavg("fcf_margin")
    w_nde = _wavg("net_debt_ebitda")
    w_cagr = _wavg("rev_cagr_5y")

    # Top: 4 big numbers vs SPY median
    def _chip(label: str, value: Optional[float], bench: float,
              fmt: str, higher_better: bool) -> str:
        color = _ratio_color(value, bench, higher_better=higher_better)
        if value is None or not math.isfinite(value):
            val_str = "—"
            bench_str = f"vs SPY {fmt % bench}"
        else:
            val_str = fmt % value
            bench_str = f"vs SPY {fmt % bench}"
        return (
            f'<div data-testid="stMetric">'
            f'<div style="color:var(--text-muted); font-size:11px; '
            f'letter-spacing:0.6px; text-transform:uppercase;">{label}</div>'
            f'<div style="color:{color}; font-size:24px; font-weight:500; '
            f'letter-spacing:-0.3px; margin-top:2px;">{val_str}</div>'
            f'<div style="color:var(--text-muted); font-size:10px; '
            f'margin-top:2px;">{bench_str}</div></div>'
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_chip("WEIGHTED ROIC",
                       None if w_roic is None else w_roic * 100,
                       _SPY_BENCH["roic"] * 100,
                       "%.1f%%", higher_better=True),
                unsafe_allow_html=True)
    c2.markdown(_chip("WEIGHTED FCF MARGIN",
                       None if w_fcfm is None else w_fcfm * 100,
                       _SPY_BENCH["fcf_margin"] * 100,
                       "%.1f%%", higher_better=True),
                unsafe_allow_html=True)
    c3.markdown(_chip("WEIGHTED NET DEBT / EBITDA", w_nde,
                       _SPY_BENCH["net_debt_ebitda"],
                       "%.2fx", higher_better=False),
                unsafe_allow_html=True)
    c4.markdown(_chip("WEIGHTED REV CAGR 5Y",
                       None if w_cagr is None else w_cagr * 100,
                       _SPY_BENCH["rev_cagr_5y"] * 100,
                       "%.1f%%", higher_better=True),
                unsafe_allow_html=True)

    # ---- Per-holding flags ----
    flags = []
    for tkr, m in per_ticker.items():
        reasons = []
        if (m.get("net_debt_ebitda") is not None
                and m["net_debt_ebitda"] > 3.0):
            reasons.append(f"leverage ND/EBITDA {m['net_debt_ebitda']:.2f}x")
        if m.get("ttm_fcf") is not None and m["ttm_fcf"] < 0:
            reasons.append(f"cash burn (FCF ${m['ttm_fcf']/1e9:+.2f}B)")
        if (m.get("roic") is not None and m["roic"] < 0.05):
            reasons.append(f"low ROIC {m['roic']*100:.1f}%")
        if reasons:
            flags.append({
                "Ticker": tkr,
                "Weight %": m["weight"] * 100,
                "Flags": " · ".join(reasons),
            })

    if flags:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px; '
            'color:rgba(184,115,51,1);">⚠ FLAGGED POSITIONS</div>',
            unsafe_allow_html=True,
        )
        df = pd.DataFrame(flags).sort_values("Weight %", ascending=False)
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={
                "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    else:
        st.caption("No leverage / cash-burn / low-ROIC flags triggered "
                   "on any position.")
