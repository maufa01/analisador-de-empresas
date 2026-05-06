"""
Universal analysis resolver.

Single entry point: ``resolve(ticker)`` classifies the ticker, routes
to the appropriate handler, and returns a uniform ``ResolverResult``
the page can switch on without inspecting the underlying providers.

Result shape (always populated, never raises):
    ResolverResult(
        ticker:    str,
        type:      TickerType,
        ui_mode:   "full" | "full_bank" | "full_reit" | "full_insurance"
                  | "etf" | "partial" | "informational" | "error",
        warnings:  list[str],
        explanation: str  (only for informational mode)
        sector_data: dict (only for full_bank / full_reit / full_insurance)
        etf_data:    dict (only for etf)
    )

The page uses ``ui_mode`` to pick the right view component. Standard
US tickers fall through to the existing pipeline (full mode); banks /
REITs render a sector-specific dashboard above the standard tabs;
ETFs / crypto / indices show informational placeholders.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

import logging

from data.ticker_classifier import (
    TickerType, TickerClassification, classify_ticker,
)

logger = logging.getLogger(__name__)


# ============================================================
# Result type
# ============================================================
@dataclass
class ResolverResult:
    ticker:        str
    type:          TickerType
    ui_mode:       str
    warnings:      list[str]                  = field(default_factory=list)
    explanation:   str                        = ""
    classification: Optional[TickerClassification] = None

    # Sector-specific payloads (populated only when relevant)
    sector_data:   Optional[dict[str, Any]]   = None
    etf_data:      Optional[dict[str, Any]]   = None


# ============================================================
# Explanations for informational mode
# ============================================================
_EXPLANATIONS: dict[TickerType, str] = {
    TickerType.CRYPTO: (
        "Cryptocurrency assets do not have financial statements. They are "
        "decentralised digital assets without underlying business operations. "
        "Price history works; income statements, DCF and ratios do not apply."
    ),
    TickerType.INDEX: (
        "This is a market index, not a company. Indices track a basket of "
        "stocks (e.g. ^GSPC = S&P 500) and have no own financials. Search the "
        "individual ticker symbols to analyse the underlying constituents."
    ),
    TickerType.MUTUAL_FUND: (
        "Mutual funds are pooled investment vehicles that hold a portfolio "
        "of securities. They expose NAV (Net Asset Value) and an expense "
        "ratio rather than income statements or balance sheets."
    ),
}


# ============================================================
# Sector handlers (best-effort wrappers — return {} on failure)
# ============================================================
def _bank_data(ticker: str) -> dict:
    try:
        from analysis.bank_analysis import analyze_bank
        return analyze_bank(ticker) or {}
    except Exception as e:
        logger.debug(f"bank_analysis failed for {ticker}: {e}")
        return {}


def _reit_data(ticker: str) -> dict:
    try:
        from analysis.reit_analysis import analyze_reit
        return analyze_reit(ticker) or {}
    except Exception as e:
        logger.debug(f"reit_analysis failed for {ticker}: {e}")
        return {}


def _insurance_data(ticker: str) -> dict:
    try:
        from analysis.insurance_analysis import analyze_insurance
        return analyze_insurance(ticker) or {}
    except Exception as e:
        logger.debug(f"insurance_analysis failed for {ticker}: {e}")
        return {}


def _etf_data(ticker: str) -> dict:
    try:
        from analysis.etf_simple import analyze_etf_simple
        return analyze_etf_simple(ticker) or {}
    except Exception as e:
        logger.debug(f"etf_simple failed for {ticker}: {e}")
        return {}


# ============================================================
# Public API
# ============================================================
def resolve(ticker: str) -> ResolverResult:
    """Classify + route. Always returns a ResolverResult; never raises."""
    classification = classify_ticker(ticker)
    t = classification.type
    norm = classification.ticker

    # ---- Standard US common stock — full pipeline path ----
    if t == TickerType.US_COMMON_STANDARD:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="full",
            warnings=list(classification.warnings),
            classification=classification,
        )

    # ---- Bank ----
    if t == TickerType.US_COMMON_BANK:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="full_bank",
            warnings=list(classification.warnings),
            classification=classification,
            sector_data=_bank_data(norm),
        )

    # ---- REIT ----
    if t == TickerType.US_COMMON_REIT:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="full_reit",
            warnings=list(classification.warnings),
            classification=classification,
            sector_data=_reit_data(norm),
        )

    # ---- Insurance ----
    if t == TickerType.US_COMMON_INSURANCE:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="full_insurance",
            warnings=list(classification.warnings),
            classification=classification,
            sector_data=_insurance_data(norm),
        )

    # ---- ETF ----
    if t == TickerType.ETF:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="etf",
            warnings=list(classification.warnings),
            classification=classification,
            etf_data=_etf_data(norm),
        )

    # ---- ADR ----
    if t == TickerType.US_ADR:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="partial",
            warnings=list(classification.warnings),
            classification=classification,
        )

    # ---- International ----
    if t == TickerType.INTERNATIONAL:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="partial",
            warnings=list(classification.warnings),
            classification=classification,
        )

    # ---- UNKNOWN — try the partial path on yfinance data we already have ----
    if t == TickerType.UNKNOWN:
        return ResolverResult(
            ticker=norm, type=t, ui_mode="partial",
            warnings=list(classification.warnings),
            classification=classification,
        )

    # ---- Crypto / Index / Mutual Fund — informational ----
    if t in (TickerType.CRYPTO, TickerType.INDEX, TickerType.MUTUAL_FUND):
        return ResolverResult(
            ticker=norm, type=t, ui_mode="informational",
            warnings=list(classification.warnings),
            classification=classification,
            explanation=_EXPLANATIONS.get(t, ""),
        )

    # ---- Invalid / Delisted ----
    return ResolverResult(
        ticker=norm, type=t, ui_mode="error",
        warnings=list(classification.warnings) or [
            f"Ticker {norm!r} could not be classified.",
        ],
        classification=classification,
    )
