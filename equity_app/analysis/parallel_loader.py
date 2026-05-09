"""
Parallel data hydration for the Equity Analysis page.

Replaces the serial fetch sequence (price → info → financials → peers)
with a single :class:`HydratedBundle` populated by 4 worker threads.

Performance: 4 sequential fetches at ~1.5s each ≈ 6s. 4 parallel
fetches at max ≈ 1.5s. Cached for 10 min per ticker — re-clicking the
same ticker is instant.

Sequence:
1. ``quote``, ``info``, ``fmp_profile``, ``financials`` run in parallel.
2. Once those land, ``peers`` runs (it needs sector from info / profile).
3. The income statement is passed through :mod:`analysis.data_quality`
   to detect partial loads and heal them.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
import streamlit as st


@dataclass
class HydratedBundle:
    """Everything the equity analysis page needs, fetched once and shared."""
    ticker: str

    quote: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)
    fmp_profile: Optional[dict] = None

    income: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    cash: pd.DataFrame = field(default_factory=pd.DataFrame)
    financials_source: str = "—"
    income_source: str = "—"        # may differ if data_quality healed it

    peers: list = field(default_factory=list)

    sources: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    # Structured exceptions per slot — preserved so the page can render
    # a per-provider diagnostic table (DataSourceError carries .attempts
    # which is list[ProviderResult]).
    exceptions: dict[str, Exception] = field(default_factory=dict)

    @property
    def has_financials(self) -> bool:
        return not self.income.empty

    @property
    def sector(self) -> Optional[str]:
        s = self.info.get("sector") if self.info else None
        if s:
            return s
        if self.fmp_profile:
            return self.fmp_profile.get("sector")
        return None

    @property
    def market_cap(self) -> Optional[float]:
        if self.info and self.info.get("marketCap"):
            return self.info["marketCap"]
        if self.info and self.info.get("market_cap"):
            return self.info["market_cap"]
        if self.fmp_profile:
            return self.fmp_profile.get("mktCap") or self.fmp_profile.get("marketCap")
        return None


# ============================================================
# Internal task wrappers (each one survives any provider error)
# ============================================================
def _quote_task(ticker: str):
    """Returns dict on success; raises DataSourceError on full failure
    (preserving the structured ``attempts`` list)."""
    from analysis.data_adapter import get_current_price
    return get_current_price(ticker)


def _info_task(ticker: str):
    from analysis.data_adapter import get_company_info
    return get_company_info(ticker)


def _fmp_profile_task(ticker: str) -> Optional[dict]:
    try:
        from data.fmp_provider import FMPProvider
        return FMPProvider().fetch_profile(ticker)
    except Exception:
        return None


def _financials_task(ticker: str) -> Optional[Any]:
    try:
        from analysis.data_adapter import require_financials
        return require_financials(ticker)
    except Exception:
        return None


# ============================================================
# Public API
# ============================================================
# CACHE_VERSION bumps invalidate every cached HydratedBundle on deploy.
# Bump this whenever the bundle SCHEMA or the provider chain changes,
# so users on stale entries get a fresh fetch instead of seeing old
# error formats / stale data shapes.
CACHE_VERSION = 2


def load_bundle(ticker: str) -> HydratedBundle:
    """Fetch everything for ``ticker`` in parallel and return one bundle.

    Successful bundles are cached for 10 minutes per ticker. Failed
    bundles (income empty, or info missing) are NOT cached — so the
    user can retry without waiting for TTL expiry.
    """
    bundle = _load_bundle_cached(ticker, CACHE_VERSION)
    # If the cached bundle is partial (financials or info failed), force
    # a fresh fetch on the next call by clearing this entry. The retry
    # itself happens on the user's next interaction.
    if bundle.income.empty or not bundle.info:
        try:
            _load_bundle_cached.clear()
        except Exception:
            pass
    return bundle


@st.cache_data(ttl=600, show_spinner=False)
def _load_bundle_cached(ticker: str, _cache_version: int) -> HydratedBundle:
    """Internal: actual fetch + hydration. ``_cache_version`` is in the
    cache key so bumping :data:`CACHE_VERSION` invalidates every entry."""
    bundle = HydratedBundle(ticker=ticker)

    tasks = {
        "quote":       _quote_task,
        "info":        _info_task,
        "fmp_profile": _fmp_profile_task,
        "financials":  _financials_task,
    }

    # ---- Parallel batch (4 independent fetches) ----
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="hydrate") as pool:
        futures = {pool.submit(fn, ticker): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:
                bundle.errors[name] = f"{type(exc).__name__}: {exc}"
                # Preserve the structured exception (DataSourceError carries
                # .attempts which the page renders as a per-provider table).
                bundle.exceptions[name] = exc
                continue

            if name == "quote":
                bundle.quote = result or {}
            elif name == "info":
                bundle.info = result or {}
            elif name == "fmp_profile":
                bundle.fmp_profile = result
            elif name == "financials":
                if result is not None:
                    bundle.income = getattr(result, "income", pd.DataFrame())
                    bundle.balance = getattr(result, "balance", pd.DataFrame())
                    bundle.cash = getattr(result, "cash", pd.DataFrame())
                    bundle.financials_source = getattr(result, "source", "—")
                    bundle.income_source = bundle.financials_source

    # ---- Income-statement quality check ----
    if not bundle.income.empty:
        try:
            from analysis.data_quality import require_complete_income
            healed, src = require_complete_income(
                ticker, bundle.income, bundle.income_source,
                # No fallback chain here — we already used data_adapter's
                # full chain. Healing alone catches the SEC-XBRL label
                # mismatch case the spec calls out.
            )
            bundle.income = healed
            bundle.income_source = src
        except Exception as exc:
            bundle.errors["data_quality"] = f"{type(exc).__name__}: {exc}"

    # ---- Peers (sequential — needs sector from the parallel batch) ----
    sector = bundle.sector
    try:
        from data.peer_resolver import fetch_live_peers
        bundle.peers = fetch_live_peers(ticker, sector)
    except Exception as exc:
        bundle.errors["peers"] = f"{type(exc).__name__}: {exc}"

    # Surface a one-line summary for telemetry
    bundle.sources = {
        "quote":       bundle.quote.get("source", "—") if bundle.quote else "—",
        "info":        bundle.info.get("source", "—") if bundle.info else "—",
        "financials":  bundle.income_source,
        "fmp_profile": "fmp" if bundle.fmp_profile else "—",
        "peers":       f"{len(bundle.peers)} resolved" if bundle.peers else "0",
    }

    return bundle
