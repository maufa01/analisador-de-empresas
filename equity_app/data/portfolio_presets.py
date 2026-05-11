"""Themed portfolio presets for the Portfolio page input UX.

Hand-picked baskets that cover the most common "show me a [theme]
portfolio" requests — growth, income, defensive, cyclical, sector
concentrate, thematic. Each preset is intentionally small (5-7
holdings) because the page's analytics break down beyond ~20 names
and these are meant as starting points, not optimised portfolios.
"""
from __future__ import annotations


PORTFOLIO_PRESETS: dict[str, dict] = {
    "Tech Mega Caps": {
        "tickers": ["MSFT", "AAPL", "NVDA", "GOOG", "META", "AMZN"],
        "description": "FAANGM core. Growth, dominant moats, tech sector.",
        "theme": "Growth",
    },
    "Dividend Aristocrats": {
        "tickers": ["KO", "PG", "JNJ", "MMM", "PEP", "MCD", "WMT"],
        "description": "25+ year dividend growers. Mature cash machines.",
        "theme": "Income",
    },
    "Defensive / Low Vol": {
        "tickers": ["KO", "PG", "JNJ", "WMT", "COST", "PEP"],
        "description": "Recession-resistant. Staples + select healthcare.",
        "theme": "Defensive",
    },
    "Energy Cyclicals": {
        "tickers": ["XOM", "CVX", "COP", "OXY", "SLB"],
        "description": "Oil & gas majors + services. Commodity-driven.",
        "theme": "Cyclical",
    },
    "Big Banks": {
        "tickers": ["JPM", "BAC", "WFC", "C", "GS"],
        "description": "US money-center banks. Rate-sensitive.",
        "theme": "Financials",
    },
    "Healthcare Mega Caps": {
        "tickers": ["UNH", "JNJ", "LLY", "MRK", "ABBV", "PFE"],
        "description": "Pharma + insurer concentrate. Aging demographics tailwind.",
        "theme": "Defensive Growth",
    },
    "Consumer Discretionary": {
        "tickers": ["AMZN", "HD", "MCD", "NKE", "SBUX", "TJX"],
        "description": "Discretionary spend leaders. Consumer cycle exposed.",
        "theme": "Cyclical",
    },
    "Industrials": {
        "tickers": ["HON", "CAT", "DE", "RTX", "GE", "UPS"],
        "description": "Industrial economy proxies. Capex + global trade.",
        "theme": "Cyclical",
    },
    "Quality Compounders": {
        # ORCL instead of BRK-B (BRK-B dash convention is inconsistent
        # across yfinance versions and reliably resolves on FMP only).
        "tickers": ["MSFT", "MA", "V", "ADBE", "COST", "ORCL"],
        "description": "High ROIC, low capex, durable advantages.",
        "theme": "Quality",
    },
    "AI / Compute Theme": {
        "tickers": ["NVDA", "AVGO", "AMD", "TSM", "MSFT", "GOOG"],
        "description": "AI hardware + hyperscaler concentrate.",
        "theme": "Thematic",
    },
    "Balanced 5-Sector": {
        "tickers": ["AAPL", "JPM", "UNH", "KO", "XOM"],
        "description": "One large-cap per major sector. Sanity baseline.",
        "theme": "Balanced",
    },
}


def get_preset(name: str) -> dict:
    """Return preset dict or empty dict if unknown."""
    return PORTFOLIO_PRESETS.get(name, {})
