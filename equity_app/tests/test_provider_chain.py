"""
analysis/data_adapter.py — provider chain + status detection tests.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from core.provider_status import ProviderResult, ProviderStatus
from analysis.data_adapter import (
    DataSourceError,
    _diagnose_failure,
    _info_from_yfinance,
    get_company_info,
    get_current_price,
)


# ============================================================
# yfinance scrape-block detection
# ============================================================
class TestScrapeBlockDetection:

    def test_sparse_info_dict_flagged(self):
        """A near-empty info dict (1-3 keys) is the typical Yahoo
        scrape-block response. Must be flagged, not silently passed."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"trailingPegRatio": None}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _info_from_yfinance("AAPL")

        assert result.status == ProviderStatus.SCRAPE_BLOCKED
        assert "1 keys" in result.message or "scrape-block" in result.message.lower()

    def test_keys_present_but_no_name_flagged(self):
        """Even with many keys, if longName/shortName are both missing
        the response is unusable — flag as scrape_blocked."""
        # 30 keys but no name fields
        mock_ticker = MagicMock()
        mock_ticker.info = {f"key_{i}": i for i in range(30)}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _info_from_yfinance("AAPL")

        assert result.status == ProviderStatus.SCRAPE_BLOCKED
        assert "longName" in result.message

    def test_healthy_response_returns_ok(self):
        mock_info = {f"k{i}": i for i in range(30)}
        mock_info["longName"] = "Apple Inc."
        mock_info["sector"] = "Technology"
        mock_info["industry"] = "Consumer Electronics"
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _info_from_yfinance("AAPL")

        assert result.status == ProviderStatus.OK
        assert result.data["name"] == "Apple Inc."


# ============================================================
# Chain fall-through
# ============================================================
class TestChainFallthrough:

    def test_falls_to_yfinance_when_fmp_missing_key(self):
        """If FMP returns MISSING_KEY, chain should try yfinance next."""
        ok_data = {"name": "Apple Inc.", "sector": "Technology"}
        with patch("analysis.data_adapter._info_from_fmp",
                   return_value=ProviderResult("fmp", ProviderStatus.MISSING_KEY,
                                                message="no key")), \
             patch("analysis.data_adapter._info_from_yfinance",
                   return_value=ProviderResult("yfinance", ProviderStatus.OK,
                                                data=ok_data)), \
             patch("analysis.data_adapter._info_from_finnhub",
                   return_value=ProviderResult("finnhub", ProviderStatus.MISSING_KEY)):
            info = get_company_info("AAPL")

        assert info["name"] == "Apple Inc."
        # providers_tried should include both fmp (failed) and yfinance (succeeded)
        labels = info["providers_tried"]
        assert any("fmp" in lbl for lbl in labels)
        assert any("yfinance" in lbl for lbl in labels)

    def test_all_failed_raises_data_source_error(self):
        with patch("analysis.data_adapter._info_from_fmp",
                   return_value=ProviderResult("fmp", ProviderStatus.MISSING_KEY)), \
             patch("analysis.data_adapter._info_from_yfinance",
                   return_value=ProviderResult("yfinance", ProviderStatus.MISSING_KEY)), \
             patch("analysis.data_adapter._info_from_finnhub",
                   return_value=ProviderResult("finnhub", ProviderStatus.MISSING_KEY)):
            with pytest.raises(DataSourceError) as exc_info:
                get_company_info("XYZ")

        # The error carries the full attempts list for the UI to render
        assert len(exc_info.value.attempts) == 3
        # Diagnostic message mentions MISSING_KEY remediation
        msg = str(exc_info.value)
        assert "FMP_API_KEY" in msg or "MISSING_KEY" in msg

    def test_first_ok_short_circuits(self):
        """If FMP succeeds, yfinance and Finnhub should NOT be called."""
        ok_data = {"name": "Apple Inc.", "sector": "Technology"}
        yf_mock = MagicMock(return_value=ProviderResult("yfinance", ProviderStatus.OK))
        fh_mock = MagicMock(return_value=ProviderResult("finnhub", ProviderStatus.OK))

        with patch("analysis.data_adapter._info_from_fmp",
                   return_value=ProviderResult("fmp", ProviderStatus.OK,
                                                data=ok_data)), \
             patch("analysis.data_adapter._info_from_yfinance", yf_mock), \
             patch("analysis.data_adapter._info_from_finnhub", fh_mock):
            info = get_company_info("AAPL")

        assert info["name"] == "Apple Inc."
        assert yf_mock.call_count == 0
        assert fh_mock.call_count == 0


# ============================================================
# Diagnostic messages
# ============================================================
class TestDiagnose:

    def test_all_missing_key_suggests_env_vars(self):
        attempts = [
            ProviderResult("fmp",      ProviderStatus.MISSING_KEY),
            ProviderResult("yfinance", ProviderStatus.MISSING_KEY),
            ProviderResult("finnhub",  ProviderStatus.MISSING_KEY),
        ]
        msg = _diagnose_failure("AAPL", attempts, kind="info")
        assert "FMP_API_KEY" in msg

    def test_scrape_block_suggests_fmp(self):
        attempts = [
            ProviderResult("fmp",      ProviderStatus.MISSING_KEY),
            ProviderResult("yfinance", ProviderStatus.SCRAPE_BLOCKED),
            ProviderResult("finnhub",  ProviderStatus.NO_MATCH),
        ]
        msg = _diagnose_failure("AAPL", attempts, kind="info")
        assert "scrape-block" in msg.lower() or "yfinance" in msg.lower()

    def test_ticker_not_found_called_out(self):
        attempts = [
            ProviderResult("fmp",      ProviderStatus.TICKER_NOT_FOUND),
            ProviderResult("yfinance", ProviderStatus.NO_MATCH),
        ]
        msg = _diagnose_failure("XYZ", attempts, kind="info")
        assert "delisted" in msg.lower() or "invalid" in msg.lower()

    def test_rate_limit_suggests_wait(self):
        attempts = [
            ProviderResult("fmp", ProviderStatus.RATE_LIMITED),
        ]
        msg = _diagnose_failure("AAPL", attempts, kind="info")
        assert "60" in msg or "wait" in msg.lower()


# ============================================================
# DataSourceError shape
# ============================================================
class TestDataSourceError:

    def test_carries_attempts_list(self):
        attempts = [
            ProviderResult("fmp", ProviderStatus.MISSING_KEY,
                            message="no key", latency_ms=12.0),
        ]
        exc = DataSourceError("boom", ["fmp:missing_key (12ms)"], attempts)
        assert exc.attempts == attempts
        assert exc.providers_tried == ["fmp:missing_key (12ms)"]

    def test_attempts_optional_for_backward_compat(self):
        """Old call sites might still pass only providers_tried."""
        exc = DataSourceError("boom", ["a", "b"])
        assert exc.attempts == []
