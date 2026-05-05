"""
DataProvider abstract interface + shared dataclasses.

Every concrete provider (Finviz, FMP, FRED, EDGAR, yfinance) implements
``DataProvider`` so that orchestration code can swap providers and fall
back through the priority chain transparently.

Why the dataclasses live here instead of next to each provider:
- They are the contract between providers and the analysis layer.
- analysis/* and valuation/* import only from data.base, never from a
  specific provider.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any

import pandas as pd


# ============================================================
# Quote — light-weight, real-time
# ============================================================
@dataclass
class Quote:
    ticker: str
    price: float
    change: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    pe: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "unknown"
    market_state: str = "unknown"  # one of: open, closed, pre, after, unknown


# ============================================================
# CompanyData — full fundamental snapshot
# ============================================================
@dataclass
class CompanyData:
    ticker: str
    info: dict = field(default_factory=dict)
    income_stmt: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cash_flow: pd.DataFrame = field(default_factory=pd.DataFrame)
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)
    key_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    ratios_provider: pd.DataFrame = field(default_factory=pd.DataFrame)
    source: str = "unknown"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- convenience accessors ----
    @property
    def name(self) -> str:
        return (
            self.info.get("companyName")
            or self.info.get("longName")
            or self.info.get("shortName")
            or self.ticker
        )

    @property
    def sector(self) -> Optional[str]:
        return self.info.get("sector")

    @property
    def industry(self) -> Optional[str]:
        return self.info.get("industry")

    @property
    def country(self) -> Optional[str]:
        return self.info.get("country")

    @property
    def currency(self) -> Optional[str]:
        return self.info.get("currency")

    @property
    def current_price(self) -> Optional[float]:
        if not self.prices.empty and "Close" in self.prices.columns:
            try:
                return float(self.prices["Close"].iloc[-1])
            except Exception:
                pass
        v = self.info.get("currentPrice") or self.info.get("regularMarketPrice")
        return float(v) if v else None

    @property
    def market_cap(self) -> Optional[float]:
        v = self.info.get("marketCap")
        return float(v) if v else None

    @property
    def shares_outstanding(self) -> Optional[float]:
        v = self.info.get("sharesOutstanding")
        return float(v) if v else None

    @property
    def beta(self) -> Optional[float]:
        v = self.info.get("beta")
        return float(v) if v else None


# ============================================================
# Provider abstract base class
# ============================================================
class DataProvider(ABC):
    """
    Abstract data provider.

    Concrete providers MUST implement fetch_quote() and fetch_company().
    Optional capabilities (news, insider, peers, screener) are declared
    via ``capabilities`` and checked by the orchestrator before dispatch.
    """

    name: str = "base"
    capabilities: frozenset[str] = frozenset({"quote", "company"})

    @abstractmethod
    def fetch_quote(self, ticker: str) -> Quote:
        """Real-time (or near-RT) quote. Raises TickerNotFoundError on miss."""

    @abstractmethod
    def fetch_company(self, ticker: str, years: int = 10) -> CompanyData:
        """Fundamental snapshot. Raises TickerNotFoundError on miss."""

    # ---- optional capabilities; default raises NotImplementedError ----

    def fetch_peers(self, ticker: str) -> list[str]:
        raise NotImplementedError(f"{self.name} does not implement peers")

    def fetch_news(self, ticker: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not implement news")

    def fetch_insider(self, ticker: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not implement insider")

    def screener(self, **filters: Any) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not implement screener")

    def is_available(self, ticker: str) -> bool:
        """Cheap availability probe — used by the orchestrator's priority chain."""
        try:
            self.fetch_quote(ticker)
            return True
        except Exception:
            return False
