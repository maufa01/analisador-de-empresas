"""
Common provider response wrapper.

Replaces the ``Optional[dict]`` pattern where ``None`` could mean any
of "no key", "rate limit", "scrape blocked", "ticker not found",
"network error". With :class:`ProviderResult` the page can show the
user a real diagnosis instead of "no-data".
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    OK = "ok"
    MISSING_KEY = "missing_key"           # API key absent or invalid
    RATE_LIMITED = "rate_limited"         # 429 / quota hit
    SCRAPE_BLOCKED = "scrape_blocked"     # yfinance returned empty / sparse
    TICKER_NOT_FOUND = "ticker_not_found"
    NETWORK_ERROR = "network_error"       # timeout / connection refused
    NO_MATCH = "no_match"                 # API responded but no data for ticker
    UNKNOWN = "unknown"


@dataclass
class ProviderResult:
    """A single provider's response — success or failure."""
    provider: str                          # "fmp" | "yfinance" | "finnhub"
    status: ProviderStatus
    data: Optional[dict] = None
    message: str = ""
    latency_ms: Optional[float] = None

    @property
    def is_ok(self) -> bool:
        return self.status == ProviderStatus.OK and self.data is not None

    def to_label(self) -> str:
        """Compact human label: ``fmp:ok (120ms)`` or ``yfinance:scrape_blocked``."""
        base = f"{self.provider}:{self.status.value}"
        if self.latency_ms is not None:
            return f"{base} ({self.latency_ms:.0f}ms)"
        return base
