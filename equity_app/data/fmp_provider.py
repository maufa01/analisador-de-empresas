"""
Financial Modeling Prep provider.

PRIMARY source for 10-year fundamentals: income, balance, cash-flow,
key-metrics, ratios, segment data, peers, historical prices.

Endpoints used (api/v3):
    /quote/{ticker}                          — quote
    /profile/{ticker}                        — sector/industry/beta/mcap
    /income-statement/{ticker}               — annual income (limit=years)
    /balance-sheet-statement/{ticker}        — annual balance
    /cash-flow-statement/{ticker}            — annual cash flow
    /key-metrics/{ticker}                    — TTM ratios
    /ratios/{ticker}                         — annual ratios
    /stock_peers?symbol={ticker}             — peer list
    /historical-price-full/{ticker}          — daily prices

Behavior:
- Token-bucket rate limiting (250/min default)
- Tenacity exponential backoff on 429/5xx
- Diskcache wrapping every public method
- Translates HTTP 404 / "Error Message" responses to TickerNotFoundError
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

try:
    import requests  # type: ignore
    _HTTP = "requests"
except ImportError:
    try:
        from urllib import request as _urllib_request  # type: ignore
        from urllib.error import HTTPError as _UrllibHTTPError  # type: ignore
        from urllib.parse import urlencode  # type: ignore
        import json as _json
        _HTTP = "urllib"
    except ImportError:
        _HTTP = None

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  # type: ignore
    _TENACITY = True
except ImportError:
    _TENACITY = False
    def retry(*_a, **_kw):  # type: ignore
        def deco(fn): return fn
        return deco
    def stop_after_attempt(*_a, **_kw): return None  # type: ignore
    def wait_exponential(*_a, **_kw): return None    # type: ignore
    def retry_if_exception_type(*_a, **_kw): return None  # type: ignore

from .base import DataProvider, Quote, CompanyData
from .cache import cached
from .rate_limiter import make_limiter
from core.config import settings
from core.constants import CACHE_TTL
from core.exceptions import (
    TickerNotFoundError,
    ProviderError,
    MissingAPIKeyError,
    RateLimitError,
)
from core.logging import get_logger

log = get_logger(__name__)

# Stable API (post Aug-2025 keys must use this; legacy /api/v3 returns 403
# with "Legacy Endpoint" message for keys created after the cutover).
# Stable endpoints accept the ticker as ?symbol=X instead of in the path.
FMP_BASE = "https://financialmodelingprep.com/stable"
_fmp_limiter = make_limiter(settings.fmp_calls_per_minute, 60)


class FMPProvider(DataProvider):
    """Financial Modeling Prep — 10y fundamentals + peers."""

    name = "fmp"
    capabilities = frozenset(
        {"quote", "company", "peers", "prices", "ratios", "key_metrics"}
    )

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.fmp_api_key
        if not self.api_key:
            log.warning("fmp_no_api_key")

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------
    @cached("quote", ttl=CACHE_TTL["quote"])
    def fetch_quote(self, ticker: str) -> Quote:
        ticker = ticker.upper().strip()
        data = self._get("quote", symbol=ticker)
        if not data:
            raise TickerNotFoundError(ticker=ticker)
        q = data[0] if isinstance(data, list) else data
        return Quote(
            ticker=ticker,
            price=float(q.get("price") or 0.0),
            change=_to_float(q.get("change")),
            change_pct=_to_float(q.get("changePercentage")),
            volume=_to_float(q.get("volume")),
            market_cap=_to_float(q.get("marketCap")),
            pe=_to_float(q.get("pe")),
            day_high=_to_float(q.get("dayHigh")),
            day_low=_to_float(q.get("dayLow")),
            week52_high=_to_float(q.get("yearHigh")),
            week52_low=_to_float(q.get("yearLow")),
            timestamp=datetime.now(timezone.utc),
            source=self.name,
        )

    def fetch_company(self, ticker: str, years: int = 5) -> CompanyData:
        ticker = ticker.upper().strip()
        try:
            profile = self.fetch_profile(ticker)
        except TickerNotFoundError:
            raise

        income = self.fetch_income_statement(ticker, years)
        balance = self.fetch_balance_sheet(ticker, years)
        cash = self.fetch_cash_flow(ticker, years)
        key_metrics = self.fetch_key_metrics(ticker, years)
        ratios_p = self.fetch_ratios(ticker, years)
        prices = self.fetch_prices(ticker, years=min(years, 5))

        info = _profile_to_info(profile)
        # Override mcap/price-derived shares with the explicit field —
        # avoids rounding errors of ~hundreds of thousands of shares
        # for large caps that propagate to per-share intrinsic value.
        if (not key_metrics.empty
                and "weightedAverageShsOut" in key_metrics.columns):
            shares_series = key_metrics["weightedAverageShsOut"].dropna()
            if not shares_series.empty:
                info["sharesOutstanding"] = float(shares_series.iloc[-1])
                info["sharesOutstandingSource"] = "key_metrics"

        return CompanyData(
            ticker=ticker,
            info=info,
            income_stmt=income,
            balance_sheet=balance,
            cash_flow=cash,
            prices=prices,
            key_metrics=key_metrics,
            ratios_provider=ratios_p,
            source=self.name,
        )

    @cached("fundamentals", ttl=CACHE_TTL["fundamentals"])
    def fetch_profile(self, ticker: str) -> dict:
        data = self._get("profile", symbol=ticker.upper().strip())
        if not data:
            raise TickerNotFoundError(ticker=ticker)
        return data[0] if isinstance(data, list) else data

    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_income_statement(self, ticker: str, years: int = 5) -> pd.DataFrame:
        data = self._get(
            "income-statement",
            symbol=ticker.upper().strip(),
            limit=years,
            period="annual",
        )
        return _to_dataframe(data)

    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_balance_sheet(self, ticker: str, years: int = 5) -> pd.DataFrame:
        data = self._get(
            "balance-sheet-statement",
            symbol=ticker.upper().strip(),
            limit=years,
            period="annual",
        )
        return _to_dataframe(data)

    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_cash_flow(self, ticker: str, years: int = 5) -> pd.DataFrame:
        data = self._get(
            "cash-flow-statement",
            symbol=ticker.upper().strip(),
            limit=years,
            period="annual",
        )
        return _to_dataframe(data)

    # ---- Quarterly variants (powering TTM column in hybrid view) ----
    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_income_statement_quarterly(
        self, ticker: str, quarters: int = 5,
    ) -> pd.DataFrame:
        try:
            data = self._get(
                "income-statement",
                symbol=ticker.upper().strip(),
                limit=quarters, period="quarter",
            )
            return _to_dataframe(data)
        except TickerNotFoundError:
            return pd.DataFrame()

    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_balance_sheet_quarterly(
        self, ticker: str, quarters: int = 5,
    ) -> pd.DataFrame:
        try:
            data = self._get(
                "balance-sheet-statement",
                symbol=ticker.upper().strip(),
                limit=quarters, period="quarter",
            )
            return _to_dataframe(data)
        except TickerNotFoundError:
            return pd.DataFrame()

    @cached("financials", ttl=CACHE_TTL["financials"])
    def fetch_cash_flow_quarterly(
        self, ticker: str, quarters: int = 5,
    ) -> pd.DataFrame:
        try:
            data = self._get(
                "cash-flow-statement",
                symbol=ticker.upper().strip(),
                limit=quarters, period="quarter",
            )
            return _to_dataframe(data)
        except TickerNotFoundError:
            return pd.DataFrame()

    @cached("fundamentals", ttl=CACHE_TTL["fundamentals"])
    def fetch_key_metrics(self, ticker: str, years: int = 5) -> pd.DataFrame:
        try:
            data = self._get(
                "key-metrics",
                symbol=ticker.upper().strip(),
                limit=years, period="annual",
            )
            return _to_dataframe(data)
        except TickerNotFoundError:
            return pd.DataFrame()

    @cached("fundamentals", ttl=CACHE_TTL["fundamentals"])
    def fetch_ratios(self, ticker: str, years: int = 5) -> pd.DataFrame:
        try:
            data = self._get(
                "ratios",
                symbol=ticker.upper().strip(),
                limit=years, period="annual",
            )
            return _to_dataframe(data)
        except TickerNotFoundError:
            return pd.DataFrame()

    @cached("fundamentals", ttl=CACHE_TTL["fundamentals"])
    def fetch_peers(self, ticker: str) -> list[str]:
        try:
            data = self._get("stock-peers", symbol=ticker.upper().strip())
        except TickerNotFoundError:
            return []
        if not data:
            return []
        # Stable shape: flat array of {symbol, companyName, price, ...}.
        # Legacy v3 shape (kept as fallback): {peersList: [...]}.
        if isinstance(data, list):
            out = []
            for entry in data:
                if isinstance(entry, dict) and entry.get("symbol"):
                    out.append(str(entry["symbol"]).upper())
                elif isinstance(entry, str):
                    out.append(entry.upper())
            return out
        if isinstance(data, dict):
            peers = data.get("peersList") or []
            return [str(p).upper() for p in peers]
        return []

    @cached("prices_eod", ttl=CACHE_TTL["prices_eod"])
    def fetch_prices(self, ticker: str, years: int = 5) -> pd.DataFrame:
        end = date.today()
        start = end - timedelta(days=years * 366)
        try:
            data = self._get(
                "historical-price-eod/full",
                symbol=ticker.upper().strip(),
                **{"from": start.isoformat(), "to": end.isoformat()},
            )
        except TickerNotFoundError:
            return pd.DataFrame()

        # Stable returns a flat list; legacy v3 wrapped it in {"historical": [...]}.
        if isinstance(data, dict):
            hist = data.get("historical") or []
        elif isinstance(data, list):
            hist = data
        else:
            return pd.DataFrame()
        if not hist:
            return pd.DataFrame()
        df = pd.DataFrame(hist)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        rename = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "adjClose": "AdjClose",
            "volume": "Volume",
        }
        df = df.rename(columns=rename)
        return df

    # ----------------------------------------------------------
    # HTTP
    # ----------------------------------------------------------
    def _check_key(self) -> None:
        if not self.api_key:
            raise MissingAPIKeyError(
                "FMP_API_KEY not configured. Get a free key at "
                "https://site.financialmodelingprep.com/developer/docs"
            )

    @retry(
        stop=stop_after_attempt(3) if _TENACITY else None,
        wait=wait_exponential(multiplier=1, min=2, max=10) if _TENACITY else None,
        reraise=True,
    )
    def _get(self, endpoint: str, **params: Any) -> Any:
        self._check_key()

        # rate limit
        if hasattr(_fmp_limiter, "try_acquire"):
            _fmp_limiter.try_acquire("fmp")
        elif hasattr(_fmp_limiter, "acquire"):
            _fmp_limiter.acquire("fmp")

        params["apikey"] = self.api_key
        url = f"{FMP_BASE}/{endpoint}"

        if _HTTP == "requests":
            r = requests.get(url, params=params, timeout=20)
            status = r.status_code
            if status == 404:
                raise TickerNotFoundError()
            if status == 429:
                raise RateLimitError("FMP rate limited (429)")
            if status in (401, 403):
                raise MissingAPIKeyError(
                    f"FMP returned {status} — API key invalid or expired"
                )
            if status >= 500:
                raise ProviderError(f"FMP {status}")
            try:
                data = r.json()
            except Exception as e:
                raise ProviderError(f"FMP non-JSON response: {e}") from e
        elif _HTTP == "urllib":
            qs = urlencode(params)
            req = _urllib_request.Request(f"{url}?{qs}", headers={"User-Agent": "equity-app/1.0"})
            try:
                with _urllib_request.urlopen(req, timeout=20) as resp:  # type: ignore
                    raw = resp.read()
            except _UrllibHTTPError as e:  # type: ignore
                if e.code == 404:
                    raise TickerNotFoundError() from e
                if e.code == 429:
                    raise RateLimitError("FMP rate limited (429)") from e
                if e.code in (401, 403):
                    raise MissingAPIKeyError(
                        f"FMP returned {e.code} — API key invalid or expired"
                    ) from e
                raise ProviderError(f"FMP {e.code}") from e
            try:
                data = _json.loads(raw)
            except Exception as e:
                raise ProviderError(f"FMP non-JSON response: {e}") from e
        else:
            raise ProviderError("No HTTP client available (requests/urllib)")

        # FMP returns {"Error Message": "..."} for unknown tickers
        if isinstance(data, dict) and data.get("Error Message"):
            raise TickerNotFoundError()

        return data


# ============================================================
# Helpers
# ============================================================
def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_dataframe(data: Any) -> pd.DataFrame:
    """FMP returns lists of dicts with 'date' field — normalize to indexed DF."""
    if not data:
        return pd.DataFrame()
    if not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
    return df


def _profile_to_info(p: dict) -> dict:
    """Normalize FMP profile to the info dict shape used across providers.

    FMP's ``lastDiv`` is the dollar amount of the most recent dividend
    (e.g. 0.96 for AAPL), NOT the yield. We compute yield from
    ``lastDiv / price`` so downstream UI can format it as a percentage.

    Shares outstanding from ``mcap / price`` introduces rounding errors
    that propagate to per-share intrinsic-value calcs — ``fetch_company``
    overrides this with ``weightedAverageShsOut`` from key-metrics.
    """
    price = _to_float(p.get("price"))
    mcap = _to_float(p.get("mktCap"))
    shares_out = (mcap / price) if (price and mcap) else None

    last_div = _to_float(p.get("lastDiv"))
    div_yield = (last_div / price) if (last_div and price and price > 0) else None

    return {
        "shortName": p.get("companyName"),
        "longName": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "country": p.get("country"),
        "currency": p.get("currency"),
        "exchange": p.get("exchangeShortName"),
        "marketCap": mcap,
        "currentPrice": price,
        "beta": _to_float(p.get("beta")),
        "trailingEps": _to_float(p.get("eps")) if "eps" in p else None,
        "sharesOutstanding": shares_out,
        "sharesOutstandingSource": "mcap_div_price" if shares_out is not None else None,
        "lastDividend": last_div,
        "dividendYield": div_yield,
        "ceo": p.get("ceo"),
        "website": p.get("website"),
        "image": p.get("image"),
        "description": p.get("description"),
        "fullTimeEmployees": p.get("fullTimeEmployees"),
        "ipoDate": p.get("ipoDate"),
    }
