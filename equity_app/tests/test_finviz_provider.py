"""
Finviz provider unit tests.

We mock the network entirely:
- ``_fundament`` is patched per-test for parsing/contract checks.
- The ``_client`` factory is patched to keep the provider import-clean
  even when finvizfinance isn't installed in the test environment.

Tests cover:
- Numeric parsers (_pf, _pp, _pv, _pmc, _range_split)
- Quote shape and source/timestamp metadata
- TickerNotFoundError on empty / failed fetch — using the literal contract
- Capability set advertises what Session 1 promises
"""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data.finviz_provider import (
    FinvizProvider,
    _pf, _pp, _pv, _pmc, _range_split,
    _fundament_to_info,
)
from data.base import Quote
from core.exceptions import TickerNotFoundError
from core.constants import TICKER_NOT_FOUND_MESSAGE


# ============================================================
# Parsers — pure functions, no network
# ============================================================
class TestParsers:

    @pytest.mark.parametrize("inp, expected", [
        ("123.45", 123.45),
        ("1,234.5", 1234.5),
        ("12.5%", 12.5),
        ("-", None),
        ("", None),
        (None, None),
        ("not-a-number", None),
    ])
    def test_pf(self, inp, expected):
        assert _pf(inp) == expected

    @pytest.mark.parametrize("inp, expected", [
        ("1.23%", 1.23),
        ("+2.5%", 2.5),
        ("-3.4%", -3.4),
        ("-", None),
    ])
    def test_pp(self, inp, expected):
        assert _pp(inp) == expected

    @pytest.mark.parametrize("inp, expected", [
        ("12,345,678", 12_345_678.0),
        ("0", 0.0),
        ("-", None),
    ])
    def test_pv(self, inp, expected):
        assert _pv(inp) == expected

    @pytest.mark.parametrize("inp, expected", [
        ("1.23B", 1.23e9),
        ("456M", 456e6),
        ("1.5T", 1.5e12),
        ("750K", 750e3),
        ("100", 100.0),
        ("-", None),
        ("", None),
    ])
    def test_pmc(self, inp, expected):
        assert _pmc(inp) == expected

    def test_range_split(self):
        assert _range_split("228.10 - 232.30", 0) == 228.10
        assert _range_split("228.10 - 232.30", 1) == 232.30
        assert _range_split("-", 0) is None
        assert _range_split("invalid", 0) is None


# ============================================================
# Info normalization
# ============================================================
class TestFundamentToInfo:

    def test_keys_present(self, make_finviz_fundament):
        info = _fundament_to_info(make_finviz_fundament())
        assert info["sector"] == "Technology"
        assert info["industry"] == "Consumer Electronics"
        assert info["marketCap"] == 3.5e12
        assert info["currentPrice"] == 230.50
        assert info["beta"] == 1.20
        assert info["currency"] == "USD"

    def test_handles_missing_fields(self):
        info = _fundament_to_info({"Company": "X"})
        assert info["shortName"] == "X"
        assert info["sector"] is None
        assert info["marketCap"] is None


# ============================================================
# fetch_quote — happy path
# ============================================================
class TestFetchQuote:

    def test_returns_quote_dataclass(self, make_finviz_fundament):
        provider = FinvizProvider()
        with patch.object(provider, "_fundament", return_value=make_finviz_fundament()):
            q = provider.fetch_quote("AAPL")

        assert isinstance(q, Quote)
        assert q.ticker == "AAPL"
        assert q.price == 230.50
        assert q.change_pct == 1.25
        assert q.market_cap == 3.5e12
        assert q.pe == 32.10
        assert q.day_low == 228.10
        assert q.day_high == 232.30
        assert q.week52_high == 240.0
        assert q.source == "finviz"
        assert isinstance(q.timestamp, datetime)
        assert q.timestamp.tzinfo == timezone.utc

    def test_uppercases_ticker(self, make_finviz_fundament):
        provider = FinvizProvider()
        with patch.object(provider, "_fundament", return_value=make_finviz_fundament()):
            q = provider.fetch_quote("aapl")
        assert q.ticker == "AAPL"


# ============================================================
# Error contract — LITERAL message
# ============================================================
class TestErrorContract:

    def test_empty_fundament_raises_with_literal_message(self):
        provider = FinvizProvider()
        with patch.object(provider, "_fundament", side_effect=TickerNotFoundError()):
            with pytest.raises(TickerNotFoundError) as exc:
                provider.fetch_quote("ZZZZ")
        # The literal contract holds at the provider boundary too.
        assert str(exc.value) == TICKER_NOT_FOUND_MESSAGE


# ============================================================
# Capabilities advertised
# ============================================================
class TestCapabilities:

    def test_capability_set(self):
        p = FinvizProvider()
        assert "quote" in p.capabilities
        assert "company" in p.capabilities
        assert "news" in p.capabilities
        assert "insider" in p.capabilities
        assert "screener" in p.capabilities
        assert "peers" in p.capabilities

    def test_name(self):
        assert FinvizProvider.name == "finviz"
