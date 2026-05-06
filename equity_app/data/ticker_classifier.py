"""
Ticker classifier — gates how the rest of the pipeline runs.

Returns a ``TickerClassification`` dataclass with:
    type:   the canonical ``TickerType`` enum value
    cik:    SEC CIK if we resolved one (None otherwise)
    country: ADR country of origin where applicable
    warnings: human-readable disclaimers the UI surfaces above analysis
    supported / unsupported features: machine-readable for the resolver

The classifier is best-effort: known-ETF / known-bank / known-REIT lists
short-circuit common cases; for everything else we hit yfinance to read
``info.quoteType`` and SEC EDGAR for a CIK lookup. When all sources fail
the result is ``TickerType.INVALID`` with a clear warning — never silent.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import logging
import re

logger = logging.getLogger(__name__)


# ============================================================
# Enum
# ============================================================
class TickerType(str, Enum):
    US_COMMON_STANDARD  = "us_common_standard"
    US_COMMON_BANK      = "us_common_bank"
    US_COMMON_REIT      = "us_common_reit"
    US_COMMON_INSURANCE = "us_common_insurance"
    US_ADR              = "us_adr"
    INTERNATIONAL       = "international"
    ETF                 = "etf"
    MUTUAL_FUND         = "mutual_fund"
    CRYPTO              = "crypto"
    INDEX               = "index"
    DELISTED            = "delisted"
    INVALID             = "invalid"
    UNKNOWN             = "unknown"


@dataclass
class TickerClassification:
    type:                  TickerType
    ticker:                str
    name:                  Optional[str] = None
    cik:                   Optional[str] = None
    country:               Optional[str] = None
    exchange:              Optional[str] = None
    quote_type:            Optional[str] = None
    warnings:              list[str]      = field(default_factory=list)
    supported_features:    list[str]      = field(default_factory=list)
    unsupported_features:  list[str]      = field(default_factory=list)


# ============================================================
# Known-set heuristics (NOT exhaustive — just fast paths)
# ============================================================
KNOWN_ETFS: set[str] = {
    "SPY", "VOO", "IVV", "QQQ", "VTI", "DIA", "IWM",
    "EFA", "EEM", "VEA", "VWO", "VXUS",
    "VNQ", "GLD", "SLV", "USO", "TLT", "AGG", "BND", "HYG", "LQD",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLB", "XLU",
    "XLC", "XLRE",
    "ARKK", "ARKW", "ARKG", "ARKF", "ARKQ",
    "VOOG", "VOOV", "VUG", "VTV", "VBR", "VBK",
    "SCHD", "SCHF", "SCHG", "SCHB", "SCHV",
    "BNDX", "MUB", "EMB", "VTEB", "JNK",
    "ROBO", "BOTZ", "HACK", "CIBR", "SKYY", "WCLD", "FINX",
    "MTUM", "QUAL", "VLUE", "USMV", "SIZE", "RPV", "RPG",
    "VYM", "DGRO", "NOBL", "DVY",
}

KNOWN_ADRS: dict[str, str] = {
    "BABA": "China", "TSM": "Taiwan", "NVO": "Denmark",
    "ASML": "Netherlands", "TM": "Japan", "SONY": "Japan",
    "SAP": "Germany", "RIO": "UK", "BP": "UK",
    "SHEL": "UK", "AZN": "UK", "GSK": "UK", "UL": "UK", "DEO": "UK",
    "NTES": "China", "JD": "China", "PDD": "China",
    "BIDU": "China", "TCEHY": "China",
    "MUFG": "Japan", "HSBC": "UK",
    "RY": "Canada", "TD": "Canada", "BNS": "Canada",
    "PHG": "Netherlands", "NSRGY": "Switzerland", "RHHBY": "Switzerland",
    "BHP": "Australia", "VALE": "Brazil", "PBR": "Brazil",
    "ITUB": "Brazil", "TKC": "Turkey",
    "STM": "Switzerland", "NIO": "China", "BCS": "UK",
    "DEO": "UK", "MELI": "Argentina/Uruguay",
}

US_BANKS: set[str] = {
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "COF",
    "BK", "STT", "SCHW", "AXP", "DFS", "ALLY",
    "FITB", "HBAN", "RF", "KEY", "CFG", "MTB", "ZION", "CMA",
    "WAL", "EWBC", "CFR", "PB", "FCNCA", "WBS", "VLY", "OZK",
    "BAC.WS", "MOFG", "FNB",
}

US_REITS: set[str] = {
    "O", "SPG", "PLD", "AMT", "CCI", "EQIX", "PSA", "WELL",
    "AVB", "EQR", "MAA", "ESS", "VTR", "INVH", "ARE", "BXP",
    "VICI", "WPC", "STAG", "CPT", "UDR", "SBAC", "EXR", "DLR",
    "HST", "REG", "FRT", "KIM", "BRX", "MAC", "SLG", "VNO",
    "HPP", "NLY", "AGNC", "MFA", "STWD", "BXMT", "LADR", "ABR",
    "ELS", "SUI", "CUBE", "LSI", "OFC", "DOC", "IRT",
}

US_INSURANCE: set[str] = {
    "BRK-A", "BRK-B", "MET", "PRU", "AIG", "ALL", "PGR", "TRV",
    "CB", "MMC", "AON", "AJG", "BRO", "AFL", "HIG", "PFG", "LNC",
    "RGA", "GL", "L", "CINF", "WRB", "ERIE", "EVR", "EG",
    "FFG", "AIZ",
}

# Common Berkshire / class-share ticker normalisations
_DOT_TO_DASH = {
    "BRK.A": "BRK-A",
    "BRK.B": "BRK-B",
    "BF.A":  "BF-A",
    "BF.B":  "BF-B",
}


# ============================================================
# Helpers
# ============================================================
def _normalise(ticker: str) -> str:
    if not ticker:
        return ""
    t = ticker.upper().strip()
    return _DOT_TO_DASH.get(t, t)


def _is_valid_format(ticker: str) -> bool:
    return bool(ticker) and bool(re.match(r"^[A-Z0-9\-\.\^]{1,12}$", ticker))


def _try_yfinance_lookup(ticker: str) -> dict:
    """Returns yfinance.info-derived fields or {} on failure. Lazy import."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    return {
        "name":       info.get("longName") or info.get("shortName"),
        "exchange":   info.get("exchange"),
        "country":    info.get("country"),
        "quote_type": (info.get("quoteType") or "").upper(),
        "category":   info.get("category"),
    }


def _try_sec_cik(ticker: str) -> Optional[str]:
    try:
        from data.edgar_provider import get_cik_for_ticker
    except Exception:
        return None
    try:
        return get_cik_for_ticker(ticker)
    except Exception:
        return None


# ============================================================
# Public API
# ============================================================
def classify_ticker(ticker: str) -> TickerClassification:
    """Classify ``ticker`` into a ``TickerType`` and return analysis hints."""
    raw = ticker
    t = _normalise(ticker)

    # ---- Invalid format ----
    if not _is_valid_format(t):
        return TickerClassification(
            type=TickerType.INVALID, ticker=t or raw,
            warnings=[f"Invalid ticker format: {raw!r}"],
        )

    # ---- Crypto (yfinance convention: BTC-USD, ETH-USD, …) ----
    if t.endswith("-USD") or t.endswith("-BTC") or t.endswith("-ETH"):
        return TickerClassification(
            type=TickerType.CRYPTO, ticker=t,
            warnings=[
                "Crypto assets — no financial statements, no DCF.",
            ],
            supported_features=["price_history"],
            unsupported_features=[
                "financials", "ratios", "dcf", "insider_transactions", "13f",
            ],
        )

    # ---- Index ----
    if t.startswith("^"):
        return TickerClassification(
            type=TickerType.INDEX, ticker=t,
            warnings=[
                "Market index — analyse individual constituents instead.",
            ],
            supported_features=["price_history"],
            unsupported_features=["everything_else"],
        )

    # ---- International (e.g. .L, .DE, .TO, .HK) — but skip .B / .A ----
    if "." in t and t not in _DOT_TO_DASH and not t.startswith("BRK"):
        suffix = t.split(".")[-1]
        # Class A/B share with dot — keep for SEC. Foreign suffix > 1 char.
        if len(suffix) > 1:
            return TickerClassification(
                type=TickerType.INTERNATIONAL, ticker=t,
                warnings=[
                    "International ticker — not in SEC EDGAR; "
                    "limited data via yfinance only.",
                ],
                supported_features=["price_history", "yfinance_basics"],
                unsupported_features=[
                    "sec_filings", "form_4_insiders", "13f_holdings",
                    "deep_historical_financials",
                ],
            )

    # ---- ETF (known set) ----
    if t in KNOWN_ETFS:
        return TickerClassification(
            type=TickerType.ETF, ticker=t,
            warnings=[
                "ETF — holds a portfolio; no own financial statements.",
            ],
            supported_features=[
                "price_history", "holdings_breakdown", "expense_ratio",
            ],
            unsupported_features=[
                "income_statement", "balance_sheet", "cash_flow",
                "ratios", "dcf", "insider_transactions",
            ],
        )

    # ---- ADR (known set) ----
    if t in KNOWN_ADRS:
        country = KNOWN_ADRS[t]
        return TickerClassification(
            type=TickerType.US_ADR, ticker=t, country=country,
            warnings=[
                f"ADR — underlying company in {country}.",
                "Files 20-F (IFRS), not 10-K. SEC Form 4 / 13F may not apply.",
            ],
            supported_features=[
                "price_history", "yfinance_financials", "news",
            ],
            unsupported_features=[
                "us_gaap_financials", "form_4_insiders",
            ],
        )

    # ---- US bank ----
    if t in US_BANKS:
        cik = _try_sec_cik(t)
        return TickerClassification(
            type=TickerType.US_COMMON_BANK, ticker=t, cik=cik,
            warnings=[
                "Bank — uses Net Interest Income / Provision for Loan Losses; "
                "gross-margin and inventory-turnover ratios don't apply.",
            ],
            supported_features=[
                "all_standard", "bank_specific_metrics",
            ],
            unsupported_features=[
                "gross_margin", "inventory_turnover", "asset_turnover_standard",
            ],
        )

    # ---- REIT ----
    if t in US_REITS:
        cik = _try_sec_cik(t)
        return TickerClassification(
            type=TickerType.US_COMMON_REIT, ticker=t, cik=cik,
            warnings=[
                "REIT — use FFO / AFFO and P/FFO instead of EPS / P/E.",
                "Standard gross-margin doesn't apply.",
            ],
            supported_features=[
                "all_standard", "ffo_affo", "reit_specific_metrics",
            ],
            unsupported_features=[
                "gross_margin", "inventory_turnover",
            ],
        )

    # ---- Insurance ----
    if t in US_INSURANCE:
        cik = _try_sec_cik(t)
        return TickerClassification(
            type=TickerType.US_COMMON_INSURANCE, ticker=t, cik=cik,
            warnings=[
                "Insurance — premium revenue, claims, combined ratio. "
                "Gross margin / inventory turnover don't apply.",
            ],
            supported_features=[
                "all_standard", "insurance_specific_metrics",
            ],
            unsupported_features=[
                "gross_margin", "inventory_turnover",
            ],
        )

    # ---- Try SEC CIK first (fastest definitive path for US common) ----
    cik = _try_sec_cik(t)
    if cik:
        return TickerClassification(
            type=TickerType.US_COMMON_STANDARD, ticker=t, cik=cik,
        )

    # ---- yfinance lookup (covers ETF/MutualFund detection + non-CIK stocks) ----
    yf_info = _try_yfinance_lookup(t)
    qt = (yf_info.get("quote_type") or "").upper()
    if qt:
        if qt == "ETF":
            return TickerClassification(
                type=TickerType.ETF, ticker=t,
                name=yf_info.get("name"),
                exchange=yf_info.get("exchange"),
                quote_type=qt,
                warnings=["ETF detected via yfinance — no own statements."],
                supported_features=[
                    "price_history", "holdings_breakdown", "expense_ratio",
                ],
                unsupported_features=[
                    "financials", "ratios", "dcf",
                ],
            )
        if qt == "MUTUALFUND":
            return TickerClassification(
                type=TickerType.MUTUAL_FUND, ticker=t,
                name=yf_info.get("name"), quote_type=qt,
                warnings=["Mutual fund — NAV / expense ratio only."],
                supported_features=["nav_history"],
                unsupported_features=["financials", "ratios", "dcf"],
            )
        if qt == "CRYPTOCURRENCY":
            return TickerClassification(
                type=TickerType.CRYPTO, ticker=t, quote_type=qt,
                warnings=["Crypto detected via yfinance — no statements."],
                supported_features=["price_history"],
                unsupported_features=["financials", "ratios", "dcf"],
            )
        if qt in ("EQUITY", "EQUITYTRUST"):
            country = yf_info.get("country")
            if country and country != "United States":
                return TickerClassification(
                    type=TickerType.US_ADR, ticker=t, country=country,
                    name=yf_info.get("name"),
                    exchange=yf_info.get("exchange"),
                    warnings=[
                        f"Foreign issuer ({country}). May report under IFRS — "
                        "SEC EDGAR coverage limited.",
                    ],
                    supported_features=["yfinance_financials", "price_history"],
                    unsupported_features=[
                        "deep_sec_filings", "form_4_insiders",
                    ],
                )
            # Non-CIK US-listed (e.g. SPAC, recent IPO before SEC mapping refresh)
            return TickerClassification(
                type=TickerType.UNKNOWN, ticker=t,
                name=yf_info.get("name"),
                exchange=yf_info.get("exchange"),
                quote_type=qt,
                warnings=[
                    "Ticker found in yfinance but not in SEC's CIK index — "
                    "limited data path will be used.",
                ],
                supported_features=["yfinance_financials", "price_history"],
                unsupported_features=["sec_form_4", "13f"],
            )

    # ---- Total miss ----
    return TickerClassification(
        type=TickerType.INVALID, ticker=t,
        warnings=[f"Ticker {t!r} not found in SEC EDGAR or yfinance."],
    )


def is_supported_for_full_analysis(c: TickerClassification) -> bool:
    """Convenience predicate — does this classification support the
    full equity-analysis pipeline (DCF, ratios, valuation, etc.)?"""
    return c.type in {
        TickerType.US_COMMON_STANDARD,
        TickerType.US_COMMON_BANK,
        TickerType.US_COMMON_REIT,
        TickerType.US_COMMON_INSURANCE,
    }
