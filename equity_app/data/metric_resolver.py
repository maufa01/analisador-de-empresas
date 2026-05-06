"""
Transparent metric resolver — yfinance first, Finnhub fallback.

When some downstream piece of the app needs a TTM ratio or per-share
figure (P/E, P/B, ROE, beta, …) and yfinance ``info`` doesn't have it,
this resolver fills the gap from Finnhub's ``stock/metric?metric=all``
without any visible UI change.

Key rules:
    - Cached 1h via the project's @cached decorator (data/cache.py).
    - Returns ``None`` instead of raising when neither source has it.
    - Never logs which key was used — a "fallback happened" event isn't
      worth the log noise; the calling code just gets a value or None.

Usage:
    from data.metric_resolver import get_metric
    pe = get_metric("AAPL", "trailing_pe")

The metric KEY (e.g. ``"trailing_pe"``) is the canonical app-side
name; the resolver maps it to (yfinance.info field name, Finnhub metric
field name).
"""
from __future__ import annotations
from typing import Any, Optional


# ============================================================
# Canonical metric → (yfinance.info field, Finnhub metric field)
# Both can be None if that source doesn't expose the metric.
# ============================================================
_METRIC_MAP: dict[str, tuple[Optional[str], Optional[str]]] = {
    # Per-share
    "eps_ttm":              ("trailingEps",                 "epsInclExtraItemsTTM"),
    "eps_forward":          ("forwardEps",                  None),
    "book_value_per_share": ("bookValue",                   "bookValuePerShareQuarterly"),
    # Multiples
    "trailing_pe":          ("trailingPE",                  "peTTM"),
    "forward_pe":           ("forwardPE",                   None),
    "price_to_book":        ("priceToBook",                 "pbQuarterly"),
    "price_to_sales":       ("priceToSalesTrailing12Months", "psTTM"),
    "ev_ebitda":            ("enterpriseToEbitda",          "currentEv/freeCashFlowTTM"),
    "ev_revenue":           ("enterpriseToRevenue",         None),
    # Profitability
    "return_on_equity":     ("returnOnEquity",              "roeTTM"),
    "return_on_assets":     ("returnOnAssets",              "roaTTM"),
    "operating_margin":     ("operatingMargins",            "operatingMarginTTM"),
    "profit_margin":        ("profitMargins",               "netProfitMarginTTM"),
    "gross_margin":         ("grossMargins",                "grossMarginTTM"),
    # Growth
    "revenue_growth_yoy":   ("revenueGrowth",               "revenueGrowthTTMYoy"),
    "earnings_growth_yoy":  ("earningsGrowth",              "epsGrowthTTMYoy"),
    # Risk / leverage
    "beta":                 ("beta",                        "beta"),
    "debt_to_equity":       ("debtToEquity",                "totalDebt/totalEquityQuarterly"),
    "current_ratio":        ("currentRatio",                "currentRatioQuarterly"),
    "quick_ratio":          ("quickRatio",                  "quickRatioQuarterly"),
    # Yield
    "dividend_yield":       ("dividendYield",               "currentDividendYieldTTM"),
    "payout_ratio":         ("payoutRatio",                 "payoutRatioTTM"),
    # 52-week
    "fifty_two_week_high":  ("fiftyTwoWeekHigh",            "52WeekHigh"),
    "fifty_two_week_low":   ("fiftyTwoWeekLow",             "52WeekLow"),
}


# ============================================================
# Optional cache wrapper — pass-through if cache module is missing
# ============================================================
def _cached_or_passthrough(prefix: str, ttl_sec: int):
    try:
        from data.cache import cached as _cached
        return _cached(prefix, ttl_sec)
    except Exception:
        def passthrough(fn):
            return fn
        return passthrough


# ============================================================
# Source readers
# ============================================================
def _from_yfinance(ticker: str, info_field: Optional[str]) -> Optional[float]:
    if not info_field:
        return None
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return None
    val = info.get(info_field)
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:                                 # NaN
        return None
    return f


def _from_finnhub(ticker: str, finnhub_field: Optional[str]) -> Optional[float]:
    if not finnhub_field:
        return None
    try:
        from data.finnhub_provider import is_available, fetch_basic_financials
    except Exception:
        return None
    if not is_available():
        return None
    try:
        payload = fetch_basic_financials(ticker) or {}
    except Exception:
        return None
    metrics = payload.get("metric") if isinstance(payload, dict) else None
    if not isinstance(metrics, dict):
        return None
    val = metrics.get(finnhub_field)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ============================================================
# Public API
# ============================================================
@_cached_or_passthrough("metric_resolver", ttl_sec=3600)
def get_metric(ticker: str, metric_key: str) -> Optional[float]:
    """
    Resolve a canonical metric for a ticker.

    Returns:
        float when at least one source had a usable value, None otherwise.
    """
    if not ticker or metric_key not in _METRIC_MAP:
        return None
    yf_field, fh_field = _METRIC_MAP[metric_key]
    val = _from_yfinance(ticker, yf_field)
    if val is not None:
        return val
    return _from_finnhub(ticker, fh_field)


def list_supported_metrics() -> list[str]:
    """Names of every canonical metric the resolver knows about."""
    return list(_METRIC_MAP.keys())
