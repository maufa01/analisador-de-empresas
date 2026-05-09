"""
Peer resolution with cascading fallback:

1. FMP ``/stock_peers`` (paid tier — best peers when available)
2. Same-sector tickers from :data:`data.constituents.META`
3. Hardcoded sector → top-5 tickers map (last-resort default)

Each resolved ticker is then hydrated **in parallel** with profile +
key-metrics fetches so the returned :class:`PeerSnapshot` has revenue,
market cap, EBITDA etc. — not just a symbol.

The page should call :func:`fetch_live_peers` (single end-to-end entry
point); the underlying helpers are exposed for tests and the parallel
loader.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from data.constituents import META as TICKER_META
from valuation.comparables import PeerSnapshot


# ============================================================
# Hardcoded fallback — top mega-caps per GICS sector
# ============================================================
SECTOR_DEFAULT_PEERS: dict[str, list[str]] = {
    "Technology":             ["AAPL", "MSFT", "NVDA", "GOOGL", "ORCL"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS"],
    "Consumer Cyclical":      ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Defensive":     ["WMT", "PG", "KO", "PEP", "COST"],
    "Consumer Staples":       ["WMT", "PG", "KO", "PEP", "COST"],
    "Financial Services":     ["JPM", "BAC", "WFC", "GS", "MS"],
    "Financials":             ["JPM", "BAC", "WFC", "GS", "MS"],
    "Healthcare":             ["JNJ", "UNH", "LLY", "PFE", "ABBV"],
    "Industrials":            ["CAT", "GE", "RTX", "HON", "UPS"],
    "Energy":                 ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Utilities":              ["NEE", "DUK", "SO", "AEP", "EXC"],
    "Real Estate":            ["AMT", "PLD", "EQIX", "WELL", "PSA"],
    "Basic Materials":        ["LIN", "SHW", "APD", "ECL", "FCX"],
    "Materials":              ["LIN", "SHW", "APD", "ECL", "FCX"],
}


# ============================================================
# Resolution
# ============================================================
def resolve_peers(
    ticker: str,
    sector: Optional[str],
    *,
    max_peers: int = 5,
) -> list[str]:
    """Return list of peer tickers via cascading fallback. Always returns
    a list (possibly empty) — never raises for missing keys / providers."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return []

    # ---- 1. FMP /stock_peers (paid tier) ----
    try:
        from data.fmp_provider import FMPProvider
        prov = FMPProvider()
        fmp_peers = prov.fetch_peers(ticker) or []
        if fmp_peers:
            return [p for p in fmp_peers if p != ticker][:max_peers]
    except Exception:
        pass

    # ---- 2. Same-sector tickers from local META (S&P 500) ----
    if sector:
        same_sector = [
            sym for sym, meta in TICKER_META.items()
            if meta.get("sector") == sector and sym != ticker
        ]
        if same_sector:
            return same_sector[:max_peers]

    # ---- 3. Hardcoded sector defaults ----
    if sector and sector in SECTOR_DEFAULT_PEERS:
        return [p for p in SECTOR_DEFAULT_PEERS[sector] if p != ticker][:max_peers]

    return []


# ============================================================
# Hydration
# ============================================================
def _hydrate_one(t: str) -> PeerSnapshot:
    """Fetch profile + key-metrics for one ticker. Survives any provider
    error by returning a snapshot with just the ticker filled in."""
    try:
        from data.fmp_provider import FMPProvider
        prov = FMPProvider()
        profile = prov.fetch_profile(t)
        km = prov.fetch_key_metrics(t, years=2)
    except Exception:
        return PeerSnapshot(ticker=t)

    mcap = profile.get("mktCap") or profile.get("marketCap")
    revenue = ebitda = ev = None
    net_income = book_value = revenue_yoy = None

    if km is not None and not km.empty:
        last = km.iloc[-1]

        def _f(key):
            v = last.get(key) if hasattr(last, "get") else None
            try:
                if v is None:
                    return None
                fv = float(v)
                return fv if fv else None
            except (TypeError, ValueError):
                return None

        ev = _f("enterpriseValue")
        ev_to_sales = _f("evToSales")
        ev_to_ebitda = _f("evToEBITDA")

        if ev and ev_to_sales:
            revenue = ev / ev_to_sales
        if ev and ev_to_ebitda:
            ebitda = ev / ev_to_ebitda

        # Net income via earnings yield × fiscal market cap
        fiscal_mcap = _f("marketCap")
        earnings_yield = _f("earningsYield")
        net_income = None
        if fiscal_mcap and earnings_yield:
            net_income = fiscal_mcap * earnings_yield

        # Book value via ROE
        roe = _f("returnOnEquity")
        book_value = None
        if net_income and roe and roe > 0:
            book_value = net_income / roe

        # Revenue YoY from prev-year row of key_metrics
        revenue_yoy = None
        if len(km) >= 2:
            prev = km.iloc[-2]
            try:
                prev_ev = float(prev.get("enterpriseValue") or 0)
                prev_evs = float(prev.get("evToSales") or 0)
                if prev_ev > 0 and prev_evs > 0 and revenue:
                    prev_revenue = prev_ev / prev_evs
                    if prev_revenue > 0:
                        revenue_yoy = (revenue / prev_revenue - 1.0) * 100.0
            except (TypeError, ValueError):
                revenue_yoy = None

    return PeerSnapshot(
        ticker=t,
        market_cap=mcap if (mcap is not None and float(mcap) > 0) else None,
        enterprise_value=ev,
        revenue=revenue,
        ebitda=ebitda,
        net_income=net_income,
        book_value=book_value,
        revenue_yoy=revenue_yoy,
    )


def hydrate_peers(peer_tickers: list[str]) -> list[PeerSnapshot]:
    """Hydrate every ticker in parallel via a 4-worker pool."""
    if not peer_tickers:
        return []
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(_hydrate_one, peer_tickers))


# ============================================================
# End-to-end entry point
# ============================================================
def fetch_live_peers(
    ticker: str,
    sector: Optional[str],
    *,
    max_peers: int = 5,
) -> list[PeerSnapshot]:
    """Resolve + hydrate. The page calls this and gets fully populated
    PeerSnapshots — no follow-up fetches needed downstream."""
    symbols = resolve_peers(ticker, sector, max_peers=max_peers)
    return hydrate_peers(symbols)
