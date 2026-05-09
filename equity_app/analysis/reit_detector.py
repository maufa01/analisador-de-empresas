"""
Single-purpose detector: is this ticker a REIT?

REITs distribute ≥90% of net income by mandate, so they don't accumulate
capital and FCFF DCF gives nonsense. The right multiples are P/FFO,
P/AFFO, NAV.

Real estate developers (DHI, LEN, PHM, KBH) are NOT REITs even though
they sit in the Real Estate sector — their industry is "Residential
Construction" / "Real Estate - Diversified", which the detector
intentionally does not match.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


KNOWN_REITS = {
    # Cell towers / infrastructure
    "AMT", "CCI", "SBAC",
    # Industrial / logistics
    "PLD", "DRE", "EXR", "PSA",
    # Data centers
    "EQIX", "DLR",
    # Healthcare
    "WELL", "VTR", "PEAK", "OHI", "MPW",
    # Residential
    "EQR", "AVB", "ESS", "MAA", "UDR", "INVH",
    # Retail
    "O", "SPG", "REG", "FRT", "KIM", "BRX",
    # Office
    "BXP", "ARE", "VNO", "HIW", "CUZ",
    # Specialty / hotels
    "VICI", "GLPI", "EPR", "HST", "PEB",
    # Mortgage REITs
    "AGNC", "NLY", "STWD",
    # Self storage
    "CUBE", "LSI",
}


@dataclass
class REITDetectionResult:
    is_reit: bool
    confidence: float
    method: str
    detail: str = ""


def detect_reit(
    ticker: str,
    fmp_profile: Optional[dict] = None,
    yf_info: Optional[dict] = None,
) -> REITDetectionResult:
    """Multi-signal REIT detection."""
    ticker_upper = (ticker or "").upper().strip()

    # SIGNAL 1 — industry contains "REIT" (authoritative)
    industries: list[tuple[str, str]] = []
    if fmp_profile and fmp_profile.get("industry"):
        industries.append(("fmp", fmp_profile["industry"]))
    if yf_info and yf_info.get("industry"):
        industries.append(("yfinance", yf_info["industry"]))

    for source, ind in industries:
        ind_upper = ind.upper()
        if "REIT" in ind_upper or "REAL ESTATE INVESTMENT TRUST" in ind_upper:
            return REITDetectionResult(
                is_reit=True, confidence=1.0,
                method=f"industry_{source}",
                detail=f"industry='{ind}'",
            )

    # SIGNAL 2 — sector "Real Estate" (US public Real Estate is almost
    # entirely REITs; developers ship under "Residential Construction")
    sector = (
        (fmp_profile or {}).get("sector")
        or (yf_info or {}).get("sector")
        or ""
    )
    if sector == "Real Estate":
        mcap = (
            (fmp_profile or {}).get("mktCap")
            or (fmp_profile or {}).get("marketCap")
            or (yf_info or {}).get("marketCap")
            or 0
        )
        try:
            mcap_b = float(mcap) / 1e9
        except (TypeError, ValueError):
            mcap_b = 0.0
        return REITDetectionResult(
            is_reit=True, confidence=0.92,
            method="sector_real_estate",
            detail=f"Sector='Real Estate', mcap=${mcap_b:.1f}B",
        )

    # SIGNAL 3 — hardcoded list
    if ticker_upper in KNOWN_REITS:
        return REITDetectionResult(
            is_reit=True, confidence=0.95,
            method="known_list",
            detail=f"{ticker_upper} in KNOWN_REITS",
        )

    return REITDetectionResult(
        is_reit=False, confidence=0.85, method="negative",
    )


def is_reit_quick(ticker: str) -> bool:
    return (ticker or "").upper().strip() in KNOWN_REITS
