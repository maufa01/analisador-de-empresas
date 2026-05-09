"""
Single-purpose detector: is this ticker an ETF / mutual fund / closed-end
fund / similar investment vehicle?

Distinct from :mod:`analysis.security_classifier` (which covers a broader
set including REITs, utilities, banks). This module is the narrow-scope
fast path used by the Equity Analysis page hard-block.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


KNOWN_FUNDS = {
    # Broad market
    "SPY", "VOO", "IVV", "VTI", "ITOT", "SCHB",
    "QQQ", "QQQM", "ONEQ",
    "DIA", "IWM", "IWB", "IWV",
    # International
    "VEA", "VWO", "EFA", "EEM", "IEMG", "ACWI",
    # Sector ETFs
    "XLK", "XLF", "XLV", "XLE", "XLI", "XLP", "XLY", "XLB", "XLU",
    "XLRE", "XLC", "VGT", "VHT", "VFH", "VDE", "VIS", "VPU",
    # Bond ETFs
    "AGG", "BND", "TLT", "IEF", "SHY", "LQD", "HYG", "JNK", "TIP",
    # Thematic / leveraged
    "ARKK", "ARKG", "ARKQ", "ARKW", "ARKF",
    "TQQQ", "SQQQ", "SOXL", "SOXS", "TMF", "TMV",
    "UPRO", "SPXU", "UVXY", "VIXY",
    # Commodity
    "GLD", "IAU", "SLV", "USO", "UNG", "DBC",
    # Vanguard / iShares aggregates
    "VT", "VOOG", "VUG", "VTV", "VYM", "SCHD", "VIG",
    # Closed-end / preferreds
    "PFF", "PGX",
}


@dataclass
class FundDetectionResult:
    is_fund: bool
    confidence: float
    method: str
    detail: str = ""


def detect_fund(
    ticker: str,
    fmp_profile: Optional[dict] = None,
    yf_info: Optional[dict] = None,
    name: Optional[str] = None,
) -> FundDetectionResult:
    """Multi-signal detection.

    Priority:
    1. FMP isEtf flag (authoritative, 1.0)
    2. FMP isFund flag (closed-end / mutual, 1.0)
    3. yfinance quoteType ETF / MUTUALFUND / FUND (authoritative, 1.0)
    4. KNOWN_FUNDS hardcoded list (high confidence, 0.95)
    5. Name suffix heuristic (lower confidence, 0.70)
    """
    ticker_upper = (ticker or "").upper().strip()

    # SIGNAL 1 — FMP isEtf
    if fmp_profile and "isEtf" in fmp_profile:
        if fmp_profile["isEtf"] is True:
            return FundDetectionResult(
                is_fund=True, confidence=1.0,
                method="fmp_isEtf",
                detail="FMP profile flag isEtf=true",
            )

    # SIGNAL 2 — FMP isFund (closed-end, mutual)
    if fmp_profile and fmp_profile.get("isFund") is True:
        return FundDetectionResult(
            is_fund=True, confidence=1.0,
            method="fmp_isFund",
            detail="FMP profile flag isFund=true",
        )

    # SIGNAL 3 — yfinance quoteType
    if yf_info:
        qt = (yf_info.get("quoteType") or "").upper()
        if qt in ("ETF", "MUTUALFUND", "FUND"):
            return FundDetectionResult(
                is_fund=True, confidence=1.0,
                method="yf_quoteType",
                detail=f"yfinance quoteType={qt}",
            )

    # SIGNAL 4 — hardcoded list
    if ticker_upper in KNOWN_FUNDS:
        return FundDetectionResult(
            is_fund=True, confidence=0.95,
            method="known_list",
            detail=f"{ticker_upper} in KNOWN_FUNDS",
        )

    # SIGNAL 5 — name heuristic
    company_name = (
        name
        or (fmp_profile or {}).get("companyName", "")
        or (yf_info or {}).get("longName", "")
        or (yf_info or {}).get("shortName", "")
        or ""
    )
    name_upper = company_name.upper()
    fund_keywords = (
        " ETF", " FUND", " INDEX", " TRUST",
        " ISHARES", " VANGUARD", " SPDR",
        " PROSHARES", " INVESCO",
    )
    matched = next((k for k in fund_keywords if k in name_upper), None)
    if matched:
        return FundDetectionResult(
            is_fund=True, confidence=0.70,
            method="name_heuristic",
            detail=f"Name contains '{matched.strip()}'",
        )

    return FundDetectionResult(
        is_fund=False, confidence=0.85, method="negative",
    )


def is_fund_quick(ticker: str) -> bool:
    """Quick check that uses only the hardcoded list — no provider needed."""
    return (ticker or "").upper().strip() in KNOWN_FUNDS
