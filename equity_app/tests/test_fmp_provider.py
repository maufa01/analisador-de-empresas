"""
FMP provider unit tests.

Network is fully mocked at the ``_get`` boundary so tests run without
an FMP key. Tests cover:

- fetch_quote returns a Quote with the correct shape and source
- TickerNotFoundError when FMP returns "Error Message" or empty payload
- MissingAPIKeyError when no key is configured
- DataFrame normalization (date column → datetime index, sorted ascending)
- Profile→info translation preserves sector/industry/mcap
"""
from __future__ import annotations
from unittest.mock import patch
import pandas as pd
import pytest

from data.fmp_provider import FMPProvider, _to_dataframe, _profile_to_info, _to_float
from data.base import Quote
from core.exceptions import TickerNotFoundError, MissingAPIKeyError
from core.constants import TICKER_NOT_FOUND_MESSAGE


# ============================================================
# Pure helpers
# ============================================================
class TestHelpers:

    def test_to_float_passthrough(self):
        assert _to_float(1.5) == 1.5
        assert _to_float("2.5") == 2.5

    def test_to_float_handles_none(self):
        assert _to_float(None) is None
        assert _to_float("") is None

    def test_to_dataframe_empty(self):
        assert _to_dataframe([]).empty
        assert _to_dataframe(None).empty

    def test_to_dataframe_indexes_by_date(self):
        data = [
            {"date": "2022-12-31", "revenue": 100},
            {"date": "2023-12-31", "revenue": 110},
        ]
        df = _to_dataframe(data)
        assert df.index.name == "date"
        assert df.iloc[0]["revenue"] == 100  # ascending sort
        assert df.iloc[-1]["revenue"] == 110

    def test_profile_to_info(self):
        info = _profile_to_info({
            "companyName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "US",
            "currency": "USD",
            "exchangeShortName": "NASDAQ",
            "mktCap": 3.5e12,
            "price": 230.50,
            "beta": 1.20,
        })
        assert info["sector"] == "Technology"
        assert info["industry"] == "Consumer Electronics"
        assert info["marketCap"] == 3.5e12
        assert info["currentPrice"] == 230.50
        assert info["sharesOutstanding"] == pytest.approx(3.5e12 / 230.50, rel=1e-6)
        assert info["beta"] == 1.20
        assert info["currency"] == "USD"

    def test_dividend_yield_computed_from_lastdiv_and_price(self):
        """Bug regression: dividendYield must be a yield (decimal),
        not the raw lastDiv dollar amount.

        AAPL pays $0.96 dividend at $230.50 price → ~0.42% yield.
        The bug stored 0.96 directly, producing a 96% yield in the UI.
        """
        info = _profile_to_info({
            "companyName": "Apple Inc.",
            "price": 230.50,
            "mktCap": 3.5e12,
            "lastDiv": 0.96,
        })
        assert info["lastDividend"] == 0.96
        assert info["dividendYield"] == pytest.approx(0.96 / 230.50, rel=1e-6)
        assert info["dividendYield"] < 0.01  # less than 1% — sane

    def test_dividend_yield_none_when_no_dividend(self):
        info = _profile_to_info({
            "companyName": "Tesla Inc.",
            "price": 250.0,
            "mktCap": 800e9,
        })
        assert info["lastDividend"] is None
        assert info["dividendYield"] is None

    def test_dividend_yield_none_when_price_missing(self):
        info = _profile_to_info({
            "companyName": "Foo",
            "lastDiv": 1.0,
        })
        assert info["dividendYield"] is None


# ============================================================
# fetch_quote
# ============================================================
class TestFetchQuote:

    def test_happy_path(self, make_fmp_quote):
        provider = FMPProvider(api_key="dummy")
        with patch.object(provider, "_get", return_value=make_fmp_quote()):
            q = provider.fetch_quote("AAPL")

        assert isinstance(q, Quote)
        assert q.ticker == "AAPL"
        assert q.price == 230.50
        assert q.change_pct == 1.25
        assert q.market_cap == 3.5e12
        assert q.source == "fmp"
        assert q.day_high == 232.30
        assert q.week52_high == 240.0

    def test_uppercases_ticker(self, make_fmp_quote):
        provider = FMPProvider(api_key="dummy")
        with patch.object(provider, "_get", return_value=make_fmp_quote()):
            q = provider.fetch_quote("aapl")
        assert q.ticker == "AAPL"

    def test_empty_response_raises_literal(self):
        provider = FMPProvider(api_key="dummy")
        with patch.object(provider, "_get", return_value=[]):
            with pytest.raises(TickerNotFoundError) as exc:
                provider.fetch_quote("ZZZZ")
        assert str(exc.value) == TICKER_NOT_FOUND_MESSAGE

    def test_error_message_response_raises_literal(self):
        provider = FMPProvider(api_key="dummy")
        # FMP's "Error Message" is translated INSIDE _get; here we
        # simulate that translation by raising directly.
        with patch.object(provider, "_get", side_effect=TickerNotFoundError()):
            with pytest.raises(TickerNotFoundError) as exc:
                provider.fetch_quote("ZZZZ")
        assert str(exc.value) == TICKER_NOT_FOUND_MESSAGE


# ============================================================
# fetch_company
# ============================================================
class TestFetchCompany:

    def test_propagates_not_found_from_profile(self):
        provider = FMPProvider(api_key="dummy")
        with patch.object(provider, "fetch_profile", side_effect=TickerNotFoundError()):
            with pytest.raises(TickerNotFoundError) as exc:
                provider.fetch_company("ZZZZ")
        assert str(exc.value) == TICKER_NOT_FOUND_MESSAGE

    def test_assembles_company_data(self):
        provider = FMPProvider(api_key="dummy")
        profile = {
            "companyName": "Apple Inc.", "sector": "Technology",
            "industry": "Consumer Electronics", "country": "US",
            "currency": "USD", "mktCap": 3.5e12, "price": 230.50, "beta": 1.20,
        }
        empty = pd.DataFrame()
        with patch.object(provider, "fetch_profile", return_value=profile), \
             patch.object(provider, "fetch_income_statement", return_value=empty), \
             patch.object(provider, "fetch_balance_sheet", return_value=empty), \
             patch.object(provider, "fetch_cash_flow", return_value=empty), \
             patch.object(provider, "fetch_key_metrics", return_value=empty), \
             patch.object(provider, "fetch_ratios", return_value=empty), \
             patch.object(provider, "fetch_prices", return_value=empty):
            company = provider.fetch_company("AAPL", years=5)

        assert company.ticker == "AAPL"
        assert company.sector == "Technology"
        assert company.market_cap == 3.5e12
        assert company.source == "fmp"


# ============================================================
# API key handling
# ============================================================
class TestAPIKey:

    def test_missing_key_raises(self):
        provider = FMPProvider(api_key="")
        with pytest.raises(MissingAPIKeyError):
            provider._check_key()

    def test_explicit_key_used(self):
        provider = FMPProvider(api_key="explicit-key")
        assert provider.api_key == "explicit-key"


# ============================================================
# Capabilities
# ============================================================
def test_name_and_capabilities():
    assert FMPProvider.name == "fmp"
    assert "quote" in FMPProvider.capabilities
    assert "company" in FMPProvider.capabilities
    assert "peers" in FMPProvider.capabilities
    assert "prices" in FMPProvider.capabilities
