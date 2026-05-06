"""
Simple ETF view — expense ratio, AUM, category, fund family, yield —
all from yfinance.

A full holdings table comes from FMP's etf-holder endpoint
(``analysis.etf_analysis.analyze_etf_holdings``) — we expose a thin
wrapper that calls it as a best-effort second pass. When neither is
available, the panel still renders the metadata yfinance provides.
"""
from __future__ import annotations
from typing import Optional

import logging

logger = logging.getLogger(__name__)


def _yf_info(ticker: str) -> dict:
    try:
        import yfinance as yf
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def analyze_etf_simple(ticker: str) -> dict:
    info = _yf_info(ticker) or {}

    expense_ratio = info.get("annualReportExpenseRatio")
    aum = info.get("totalAssets")
    category = info.get("category")
    fund_family = info.get("fundFamily")
    yield_ = info.get("yield")

    # Top holdings + sector allocation: try FMP first, fall back to none
    holdings_top = []
    try:
        from analysis.etf_analysis import analyze_etf_holdings
        result = analyze_etf_holdings(ticker)
        if result and getattr(result, "available", False):
            holdings_top = [
                {
                    "asset":         h.asset,
                    "name":          h.name,
                    "weight_pct":    h.weight_pct,
                    "shares":        h.shares,
                    "market_value":  h.market_value,
                }
                for h in (result.top_etfs or [])[:10]
            ]
    except Exception:
        holdings_top = []

    return {
        "available":     True,
        "expense_ratio": expense_ratio,
        "aum":           aum,
        "category":      category,
        "fund_family":   fund_family,
        "yield":         yield_,
        "name":          info.get("longName") or info.get("shortName"),
        "summary":       info.get("longBusinessSummary"),
        "top_holdings":  holdings_top,
        "note": (
            "ETF metadata via yfinance. Full holdings detail requires FMP — "
            "set FMP_API_KEY to enable the holdings table."
        ),
    }
