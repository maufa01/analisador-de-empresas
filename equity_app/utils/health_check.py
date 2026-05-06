"""
API health check — pings every external provider with a tiny request
and reports status. Used by the sidebar so a misconfigured / down
provider is visible immediately, not buried behind a single page that
silently fails over.

Each check returns:
    {
        "status":     "ok" | "degraded" | "missing_key" | "error",
        "fetched_at": datetime,
        "reason":     str (only for non-ok),
        ... provider-specific extras (price / yield / count) ...
    }

Checks run in parallel via ThreadPoolExecutor. Total wall-clock cost
~10s in the worst case (when several providers are slow / timing out).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

import concurrent.futures
import logging

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# Per-provider checks
# ============================================================
def check_yfinance() -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {"status": "error", "reason": "yfinance not installed",
                "fetched_at": _now()}
    try:
        info = yf.Ticker("AAPL").fast_info
        price = float(info.get("last_price")) if info.get("last_price") else None
        if not price:
            full = yf.Ticker("AAPL").info or {}
            price = full.get("regularMarketPrice")
        if not price:
            return {"status": "degraded", "reason": "Empty quote for AAPL",
                    "fetched_at": _now()}
        return {"status": "ok", "fetched_at": _now(),
                "test_price_aapl": float(price)}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


def check_finnhub() -> dict:
    try:
        from data.finnhub_provider import is_available, fetch_quote
    except Exception:
        return {"status": "error", "reason": "finnhub_provider missing",
                "fetched_at": _now()}
    if not is_available():
        return {"status": "missing_key",
                "reason": "FINNHUB_API_KEY not configured",
                "fetched_at": _now()}
    try:
        q = fetch_quote("AAPL")
        if not isinstance(q, dict) or not q.get("c"):
            return {"status": "degraded", "reason": "Empty AAPL quote",
                    "fetched_at": _now()}
        return {"status": "ok", "fetched_at": _now(),
                "test_price_aapl": float(q["c"])}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


def check_fred() -> dict:
    try:
        from data.fred_provider import is_available, latest_value
    except Exception:
        return {"status": "error", "reason": "fred_provider missing",
                "fetched_at": _now()}
    if not is_available():
        return {"status": "missing_key",
                "reason": "FRED_API_KEY not configured",
                "fetched_at": _now()}
    try:
        v, d = latest_value("DGS10")
        if v is None:
            return {"status": "degraded", "reason": "Empty DGS10 series",
                    "fetched_at": _now()}
        return {"status": "ok", "fetched_at": _now(),
                "us_10y_yield": float(v),
                "as_of": d.isoformat() if d is not None else None}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


def check_marketaux() -> dict:
    try:
        from data.marketaux_provider import is_available, fetch_news
    except Exception:
        return {"status": "error", "reason": "marketaux_provider missing",
                "fetched_at": _now()}
    if not is_available():
        return {"status": "missing_key",
                "reason": "MARKETAUX_API_KEY not configured",
                "fetched_at": _now()}
    try:
        df = fetch_news("AAPL", limit=1)
        return {"status": "ok" if not df.empty else "degraded",
                "fetched_at": _now(),
                "articles_returned": int(len(df))}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


def check_sec_edgar() -> dict:
    try:
        from data.edgar_provider import get_cik_for_ticker
    except Exception:
        return {"status": "error", "reason": "edgar_provider missing",
                "fetched_at": _now()}
    try:
        cik = get_cik_for_ticker("AAPL")
        if not cik:
            return {"status": "degraded", "reason": "AAPL CIK lookup failed",
                    "fetched_at": _now()}
        return {"status": "ok", "fetched_at": _now(),
                "test_cik_aapl": cik}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


def check_fmp() -> dict:
    try:
        from data import fmp_extras
    except Exception:
        return {"status": "error", "reason": "fmp_extras missing",
                "fetched_at": _now()}
    if not fmp_extras.is_available():
        return {"status": "missing_key",
                "reason": "FMP_API_KEY not configured",
                "fetched_at": _now()}
    # Use a cheap endpoint — fetch_etf_holders is rate-limit-friendly
    try:
        df = fmp_extras.fetch_etf_holders("AAPL")
        return {"status": "ok" if not df.empty else "degraded",
                "fetched_at": _now(),
                "etfs_returned": int(len(df))}
    except Exception as e:
        return {"status": "error", "reason": f"{type(e).__name__}: {e}",
                "fetched_at": _now()}


# ============================================================
# Aggregate
# ============================================================
_CHECKS = {
    "yfinance":  check_yfinance,
    "finnhub":   check_finnhub,
    "fred":      check_fred,
    "marketaux": check_marketaux,
    "sec_edgar": check_sec_edgar,
    "fmp":       check_fmp,
}


def run_full_health_check(*, timeout_s: int = 10) -> dict[str, dict]:
    """Run every provider check in parallel. Returns a dict keyed by name."""
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(_CHECKS)) as ex:
        futures = {ex.submit(fn): name for name, fn in _CHECKS.items()}
        for fut in concurrent.futures.as_completed(futures, timeout=timeout_s + 2):
            name = futures[fut]
            try:
                results[name] = fut.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                results[name] = {
                    "status": "error",
                    "reason": f"check timed out after {timeout_s}s",
                    "fetched_at": _now(),
                }
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "reason": f"{type(e).__name__}: {e}",
                    "fetched_at": _now(),
                }
    # Ensure every provider is in the result, even if its future never resolved
    for name in _CHECKS:
        results.setdefault(name, {
            "status": "error",
            "reason": "check did not complete",
            "fetched_at": _now(),
        })
    return results
