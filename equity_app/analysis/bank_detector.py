"""
Single-purpose detector: is this ticker a commercial / investment bank?

The NEVER_BLOCK_AS_BANK list explicitly excludes payment processors,
asset managers, exchanges, brokers, and rating agencies — these all sit
inside Financial Services but are operating companies that DO generate
analyzable FCF.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


KNOWN_BANKS = {
    # Money-center / large diversified
    "JPM", "BAC", "WFC", "C",
    # Investment banks (commercial banks since 2008)
    "GS", "MS",
    # Super-regional / large regional
    "USB", "PNC", "TFC", "BK", "STT", "MTB",
    # Regional banks
    "RF", "KEY", "FITB", "HBAN", "CFG", "ZION", "CMA", "WAL", "EWBC",
    "CFR", "FHN", "PNFP", "WBS", "BOKF", "PB", "VLY", "FFBC",
    # Custody / trust
    "NTRS",
    # Foreign ADRs
    "HSBC", "BCS", "DB", "CS", "UBS", "SAN", "ING", "BBVA", "BNS", "TD", "RY",
    # Schwab — became bank after USAA Bank + TD Ameritrade
    "SCHW",
}


# Tickers that look bank-adjacent but are actually operating companies
# whose FCF is analyzable. The override beats KNOWN_BANKS and any
# industry signal — explicit allow-list.
NEVER_BLOCK_AS_BANK = {
    # Payment networks
    "V", "MA", "PYPL", "FIS", "FISV", "FI", "GPN", "WU",
    # Asset managers (fee-based, generate own FCF)
    "BLK", "BX", "KKR", "APO", "ARES", "TROW", "BEN", "IVZ", "AMG", "AMP",
    # Exchanges
    "ICE", "CME", "NDAQ", "CBOE", "MKTX",
    # Full-service brokers (commission-based)
    "RJF", "LPLA",
    # Berkshire (insurance + holdings; valuation differs but operating)
    "BRK.A", "BRK.B", "BRK-A", "BRK-B",
    # Charge-card network
    "AXP",
    # Rating agencies
    "MCO", "SPGI",
    # Consumer-finance issuers (debatable; lender-style balance sheets
    # but kept as operating companies for now)
    "DFS", "COF", "SYF", "ALLY",
}


@dataclass
class BankDetectionResult:
    is_bank: bool
    confidence: float
    method: str
    detail: str = ""


def detect_bank(
    ticker: str,
    fmp_profile: Optional[dict] = None,
    yf_info: Optional[dict] = None,
) -> BankDetectionResult:
    """Multi-signal bank detection with explicit overrides."""
    ticker_upper = (ticker or "").upper().strip()

    # OVERRIDE — never-block list wins over every other signal
    if ticker_upper in NEVER_BLOCK_AS_BANK:
        return BankDetectionResult(
            is_bank=False, confidence=1.0,
            method="never_block_override",
            detail=f"{ticker_upper} in NEVER_BLOCK_AS_BANK",
        )

    # SIGNAL 1 — industry strings
    industries: list[tuple[str, str]] = []
    if fmp_profile and fmp_profile.get("industry"):
        industries.append(("fmp", fmp_profile["industry"]))
    if yf_info and yf_info.get("industry"):
        industries.append(("yfinance", yf_info["industry"]))

    bank_keywords = (
        "BANKS - DIVERSIFIED",
        "BANKS - REGIONAL",
        "BANKS - MAJOR",
        "BANKS DIVERSIFIED",
        "BANKS REGIONAL",
        "MONEY CENTER",
        "COMMERCIAL BANK",
        "SAVINGS BANK",
        "THRIFT",
    )

    for source, ind in industries:
        ind_upper = ind.upper()
        for kw in bank_keywords:
            if kw in ind_upper:
                return BankDetectionResult(
                    is_bank=True, confidence=1.0,
                    method=f"industry_{source}",
                    detail=f"industry='{ind}' matches '{kw}'",
                )
        # Loose fallback — "Bank" word boundary, but skip Capital Markets
        # (asset managers / exchanges report as Capital Markets).
        padded = f" {ind_upper} "
        if (" BANK" in padded or "BANK " in padded) and "CAPITAL MARKETS" not in ind_upper:
            return BankDetectionResult(
                is_bank=True, confidence=0.90,
                method=f"industry_{source}_loose",
                detail=f"industry='{ind}' contains 'Bank' word",
            )

    # SIGNAL 2 — hardcoded list
    if ticker_upper in KNOWN_BANKS:
        return BankDetectionResult(
            is_bank=True, confidence=0.95,
            method="known_list",
            detail=f"{ticker_upper} in KNOWN_BANKS",
        )

    return BankDetectionResult(
        is_bank=False, confidence=0.85, method="negative",
    )


def is_bank_quick(ticker: str) -> bool:
    """Quick check using just the hardcoded lists — no provider needed."""
    t = (ticker or "").upper().strip()
    if t in NEVER_BLOCK_AS_BANK:
        return False
    return t in KNOWN_BANKS
