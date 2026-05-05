"""
Custom exception hierarchy.

TickerNotFoundError ALWAYS carries the literal user-facing message defined
in requirements section 3, rule #1 — no accents, no extra text. Tests in
tests/test_ticker_not_found.py enforce this contract.
"""
from __future__ import annotations

from .constants import TICKER_NOT_FOUND_MESSAGE


class EquityAppError(Exception):
    """Base exception for the application."""


class TickerNotFoundError(EquityAppError):
    """
    Raised when a ticker is not available in ANY data source.

    The exception's str() is locked to ``TICKER_NOT_FOUND_MESSAGE`` so that
    the UI can render `str(err)` without ever leaking internal details and
    without ever varying the wording.

    Section 3, rule #1: "perdone, no se agrego la accion"
        - No accents
        - No suggestions
        - No extra text
    """

    def __init__(self, ticker: str | None = None, original: Exception | None = None):
        super().__init__(TICKER_NOT_FOUND_MESSAGE)
        self.user_message: str = TICKER_NOT_FOUND_MESSAGE
        self.ticker = ticker          # internal use only — never shown
        self.original = original      # internal use only — never shown

    def __str__(self) -> str:
        return TICKER_NOT_FOUND_MESSAGE


class ProviderError(EquityAppError):
    """Generic provider failure (network, API contract violation, parsing)."""


class MissingAPIKeyError(EquityAppError):
    """Required API key is not configured in the environment."""


class RateLimitError(EquityAppError):
    """Provider has rate-limited us; caller should back off."""


class DataQualityError(EquityAppError):
    """Data inconsistency detected (e.g., balance sheet does not balance)."""


class ValuationError(EquityAppError):
    """Valuation model failed validation (e.g., WACC <= terminal growth)."""


class InsufficientDataError(EquityAppError):
    """Not enough data to perform the requested operation."""
