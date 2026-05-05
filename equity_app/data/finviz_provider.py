"""
Finviz provider — built on ``finvizfinance``.

Capabilities:
- Real-time quotes (Finviz delays free US equities ~15min; good enough for our 5s refresh)
- Fundamentals snapshot (P/E, P/B, margins, etc.)
- News headlines
- Insider transactions
- Sector/industry screener

This provider is the PRIMARY source for real-time quotes (rule #2) and the
PRIMARY source for the screener (rule #3). It is NOT used for 10y financials
— for that, see ``fmp_provider``.

Politeness:
- We respect a configurable min delay (``settings.finviz_delay_seconds``)
  between requests through ``MinDelayLimiter``.
- Quotes are cached for 5 seconds, so the auto-refresh fragment doesn't
  hammer Finviz for users who keep the page open.
"""
from __future__ import annotations
from datetime import datetime, time, timezone
from typing import Optional, Any

import pandas as pd

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  # type: ignore
    _TENACITY = True
except ImportError:
    _TENACITY = False
    def retry(*_args, **_kwargs):  # type: ignore
        def decorator(fn): return fn
        return decorator
    def stop_after_attempt(*_a, **_kw): return None  # type: ignore
    def wait_exponential(*_a, **_kw): return None    # type: ignore
    def retry_if_exception_type(*_a, **_kw): return None  # type: ignore

from .base import DataProvider, Quote, CompanyData
from .cache import cached
from .rate_limiter import MinDelayLimiter
from core.config import settings
from core.constants import CACHE_TTL
from core.exceptions import TickerNotFoundError, ProviderError
from core.logging import get_logger

log = get_logger(__name__)

_finviz_limiter = MinDelayLimiter(settings.finviz_delay_seconds)


class FinvizProvider(DataProvider):
    name = "finviz"
    capabilities = frozenset(
        {"quote", "company", "news", "insider", "screener", "peers"}
    )

    # ----------------------------------------------------------
    # Quote
    # ----------------------------------------------------------
    @cached("quote", ttl=CACHE_TTL["quote"])
    def fetch_quote(self, ticker: str) -> Quote:
        ticker = ticker.upper().strip()
        fund = self._fundament(ticker)

        return Quote(
            ticker=ticker,
            price=_pf(fund.get("Price")) or 0.0,
            change=None,
            change_pct=_pp(fund.get("Change")),
            volume=_pv(fund.get("Volume")),
            market_cap=_pmc(fund.get("Market Cap")),
            pe=_pf(fund.get("P/E")),
            day_high=_range_split(fund.get("Range"), 1),
            day_low=_range_split(fund.get("Range"), 0),
            week52_high=_range_split(fund.get("52W Range"), 1),
            week52_low=_range_split(fund.get("52W Range"), 0),
            timestamp=datetime.now(timezone.utc),
            source=self.name,
            market_state=detect_market_state(),
        )

    # ----------------------------------------------------------
    # Company (info-only — Finviz doesn't expose 10y financials)
    # ----------------------------------------------------------
    def fetch_company(self, ticker: str, years: int = 10) -> CompanyData:
        ticker = ticker.upper().strip()
        fund = self._fundament(ticker)
        return CompanyData(
            ticker=ticker,
            info=_fundament_to_info(fund),
            source=self.name,
        )

    # ----------------------------------------------------------
    # News
    # ----------------------------------------------------------
    @cached("news", ttl=CACHE_TTL["news"])
    def fetch_news(self, ticker: str) -> pd.DataFrame:
        try:
            f = self._client(ticker)
            df = f.ticker_news()
        except Exception as e:
            log.warning("finviz_news_failed", ticker=ticker, error=str(e))
            return pd.DataFrame()
        return df if df is not None else pd.DataFrame()

    # ----------------------------------------------------------
    # Insider transactions
    # ----------------------------------------------------------
    @cached("insider", ttl=CACHE_TTL["insider"])
    def fetch_insider(self, ticker: str) -> pd.DataFrame:
        try:
            f = self._client(ticker)
            df = f.ticker_inside_trader()
        except Exception as e:
            log.warning("finviz_insider_failed", ticker=ticker, error=str(e))
            return pd.DataFrame()
        return df if df is not None else pd.DataFrame()

    # ----------------------------------------------------------
    # Peers (industry-based — exposed by ticker_full_info or screener)
    # ----------------------------------------------------------
    def fetch_peers(self, ticker: str) -> list[str]:
        # Finviz doesn't have a direct peers endpoint; we re-use the screener
        # filtered by industry. This is intentionally lazy — for proper peer
        # selection use ``fmp_provider.fetch_peers``.
        try:
            fund = self._fundament(ticker)
            industry = fund.get("Industry")
            if not industry:
                return []
            df = self.screener(industry=industry)
            tickers = (
                df["Ticker"].tolist() if "Ticker" in df.columns else []
            )
            return [t for t in tickers if t.upper() != ticker.upper()][:20]
        except Exception as e:
            log.warning("finviz_peers_failed", ticker=ticker, error=str(e))
            return []

    # ----------------------------------------------------------
    # Screener (sector/industry filters)
    # ----------------------------------------------------------
    @cached("screener", ttl=CACHE_TTL["screener"])
    def screener(self, **filters: Any) -> pd.DataFrame:
        """Thin wrapper around finvizfinance.screener.overview.Overview."""
        try:
            from finvizfinance.screener.overview import Overview  # type: ignore
        except ImportError as e:
            raise ProviderError("finvizfinance not installed") from e

        _finviz_limiter.wait()
        ov = Overview()
        if filters:
            try:
                ov.set_filter(filters_dict=filters)
            except Exception as e:
                log.warning("finviz_screener_filter_invalid", filters=filters, error=str(e))
        try:
            df = ov.screener_view()
        except Exception as e:
            raise ProviderError(f"finviz screener failed: {e}") from e
        return df if df is not None else pd.DataFrame()

    # ----------------------------------------------------------
    # Internals
    # ----------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3) if _TENACITY else None,
        wait=wait_exponential(multiplier=1, min=2, max=10) if _TENACITY else None,
        reraise=True,
    )
    @cached("fundamentals", ttl=CACHE_TTL["fundamentals"])
    def _fundament(self, ticker: str) -> dict:
        try:
            f = self._client(ticker)
            fund = f.ticker_fundament()
        except Exception as e:
            log.warning("finviz_fundament_failed", ticker=ticker, error=str(e))
            raise TickerNotFoundError(ticker=ticker, original=e) from e
        if not fund:
            raise TickerNotFoundError(ticker=ticker)
        return fund

    @staticmethod
    def _client(ticker: str):
        try:
            from finvizfinance.quote import finvizfinance  # type: ignore
        except ImportError as e:
            raise ProviderError("finvizfinance not installed") from e
        _finviz_limiter.wait()
        return finvizfinance(ticker.upper().strip())


# ============================================================
# Parsing helpers
# ============================================================
def _pf(s: Any) -> Optional[float]:
    """Parse a plain Finviz numeric field ('123.45')."""
    if s in (None, "-", ""):
        return None
    try:
        return float(str(s).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def _pp(s: Any) -> Optional[float]:
    """Parse a percent field ('1.23%' -> 1.23)."""
    if s in (None, "-", ""):
        return None
    try:
        return float(str(s).replace("%", "").replace(",", "").replace("+", ""))
    except ValueError:
        return None


def _pv(s: Any) -> Optional[float]:
    """Parse a volume field ('12,345,678')."""
    if s in (None, "-", ""):
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def _pmc(s: Any) -> Optional[float]:
    """Parse a market cap field ('1.23B', '456M', '1.2T')."""
    if s in (None, "-", ""):
        return None
    s2 = str(s).strip().upper().replace(",", "")
    suffix_map = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    try:
        if s2 and s2[-1] in suffix_map:
            return float(s2[:-1]) * suffix_map[s2[-1]]
        return float(s2)
    except ValueError:
        return None


def _range_split(s: Any, idx: int) -> Optional[float]:
    """Parse 'low - high' Finviz range strings."""
    if s in (None, "-", ""):
        return None
    parts = str(s).split("-")
    if len(parts) != 2:
        return None
    return _pf(parts[idx].strip())


def _fundament_to_info(fund: dict) -> dict:
    return {
        "shortName": fund.get("Company"),
        "longName": fund.get("Company"),
        "sector": fund.get("Sector"),
        "industry": fund.get("Industry"),
        "country": fund.get("Country"),
        "marketCap": _pmc(fund.get("Market Cap")),
        "currentPrice": _pf(fund.get("Price")),
        "trailingPE": _pf(fund.get("P/E")),
        "forwardPE": _pf(fund.get("Forward P/E")),
        "pegRatio": _pf(fund.get("PEG")),
        "priceToBook": _pf(fund.get("P/B")),
        "beta": _pf(fund.get("Beta")),
        "trailingEps": _pf(fund.get("EPS (ttm)")),
        "dividendYield": _pp(fund.get("Dividend %")),
        "shortRatio": _pf(fund.get("Short Ratio")),
        "shortPercent": _pp(fund.get("Short Float")),
        "currency": "USD",
    }


# ============================================================
# Market state
# ============================================================
def detect_market_state() -> str:
    """Return: open | closed | pre | after | unknown (US equity hours, ET)."""
    try:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            try:
                import pytz  # type: ignore
                now = datetime.now(pytz.timezone("America/New_York"))
            except Exception:
                return "unknown"
    except Exception:
        return "unknown"

    if now.weekday() >= 5:
        return "closed"
    t = now.time()
    if time(4, 0) <= t < time(9, 30):
        return "pre"
    if time(9, 30) <= t < time(16, 0):
        return "open"
    if time(16, 0) <= t < time(20, 0):
        return "after"
    return "closed"
