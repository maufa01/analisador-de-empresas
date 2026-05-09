"""
Classify a ticker into operating-company vs specialised-security.

Operating companies generate FCF and the FCFF DCF model used by this
app applies cleanly. Specialised securities (REITs, utilities, banks,
insurers, BDCs, MLPs, royalty trusts, ETFs / funds) need different
valuation approaches and the FCFF DCF would produce misleading numbers.

The classifier is *cheap* — sector / industry strings + a hardcoded
shortlist of known tickers, no network calls. Page-level use: filter
the ticker dropdown + soft-block the analysis flow with an override
checkbox.

Distinct from :mod:`analysis.industry_classifier` (which is a thinner
helper used inside ``valuation_pipeline._should_skip_fcff_dcf`` for
just bank / insurance / REIT). This module is broader (also covers
utilities, MLPs, BDCs, royalty trusts, ETFs) and is the entry point
the UI / dropdown filter consumes.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SecurityType(str, Enum):
    OPERATING       = "operating"        # FCFF DCF applies
    REIT            = "reit"
    UTILITY         = "utility"
    BANK            = "bank"
    INSURANCE       = "insurance"
    BDC             = "bdc"
    MLP             = "mlp"
    FUND            = "fund"             # ETF, mutual fund, closed-end
    ROYALTY_TRUST   = "royalty_trust"
    UNKNOWN         = "unknown"


@dataclass
class SecurityClassification:
    security_type: SecurityType
    confidence: float                    # 0..1
    reason: str
    valuation_applicable: bool           # True only for OPERATING
    suggested_alternative: Optional[str] = None


# ============================================================
# Pattern banks
# ============================================================
KNOWN_ETF_TICKERS = {
    "SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "VEA", "VWO",
    "ARKK", "ARKG", "ARKQ", "TQQQ", "SQQQ", "VGT", "XLK", "XLF",
    "XLE", "XLV", "XLU", "XLP", "XLY", "XLI", "XLB", "XLC", "XLRE",
    "EEM", "EFA", "AGG", "BND", "TLT", "GLD", "SLV", "USO", "VNQ",
}
KNOWN_ETF_NAME_SUFFIXES = ("ETF", "FUND", "INDEX", "TRUST")

KNOWN_UTILITIES = {
    "DUK", "NEE", "SO", "AEP", "EXC", "D", "PCG", "ED", "XEL",
    "ETR", "WEC", "ES", "AWK", "EIX", "PEG", "FE", "PPL", "CMS",
    "DTE", "AEE", "ATO", "CNP", "EVRG", "LNT", "NRG", "PNW", "SRE",
}
KNOWN_REITS = {
    "AMT", "PLD", "EQIX", "WELL", "PSA", "O", "VICI", "SPG", "EXR",
    "AVB", "EQR", "DLR", "ARE", "VTR", "SBAC", "WY", "INVH",
    "MAA", "ESS", "UDR", "CPT", "REG", "BXP", "FRT", "KIM",
}
KNOWN_BANKS = {
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC",
    "SCHW", "BK", "STT", "FITB", "RF", "HBAN", "CFG", "KEY",
    "MTB", "ZION", "CMA", "WAL", "FHN", "PBCT",
}
KNOWN_INSURERS = {
    "BRK.B", "BRK-B", "BRK.A", "BRK-A",
    "PGR", "TRV", "AIG", "ALL", "MET", "PRU", "AFL",
    "CB", "HIG", "L", "RGA", "WRB", "ACGL", "AJG", "AON",
    "MMC", "MKL", "ZGN",
}
KNOWN_BDCS = {
    "ARCC", "MAIN", "OBDC", "BXSL", "FSK", "GBDC", "HTGC", "PSEC",
}
KNOWN_MLPS = {
    "ET", "EPD", "MPLX", "WES", "ENB", "BPMP",
}
KNOWN_ROYALTY_TRUSTS = {"SBR", "SJT", "PBT", "BPT", "DMLP"}


# Industry-keyword → SecurityType (case-insensitive substring match)
_INDUSTRY_KEYWORDS: list[tuple[str, SecurityType]] = [
    ("REIT",                       SecurityType.REIT),
    ("Real Estate Investment",     SecurityType.REIT),
    ("Insurance",                  SecurityType.INSURANCE),
    ("Reinsurance",                SecurityType.INSURANCE),
    ("Bank",                       SecurityType.BANK),
    ("Closed-End",                 SecurityType.FUND),
    ("Mutual Fund",                SecurityType.FUND),
    ("Exchange Traded",            SecurityType.FUND),
    ("Business Development",       SecurityType.BDC),
    ("Master Limited",             SecurityType.MLP),
    ("Royalty",                    SecurityType.ROYALTY_TRUST),
]

# Sector → SecurityType for clear-cut cases. Financial Services is too
# broad (covers banks + insurers + asset managers), so it's resolved at
# the industry level.
_SECTOR_TO_TYPE: dict[str, SecurityType] = {
    "Utilities":         SecurityType.UTILITY,
    "Real Estate":       SecurityType.REIT,
}


# ============================================================
# Suggested alternatives per type
# ============================================================
_ALTERNATIVES: dict[SecurityType, str] = {
    SecurityType.UTILITY:        "Use a Dividend Discount Model — utilities trade as bond proxies.",
    SecurityType.REIT:           "Use FFO / AFFO multiples — REITs distribute most income.",
    SecurityType.BANK:           "Use Residual Income or P/TBV — banks aren't valued via FCFF.",
    SecurityType.INSURANCE:      "Use Embedded Value or P/B — insurance liabilities skew FCF.",
    SecurityType.BDC:            "Use NAV — BDCs distribute substantially all income.",
    SecurityType.MLP:            "Use distribution-based valuation — MLPs aren't C-corps.",
    SecurityType.FUND:           "Funds aren't fundamentals-based; use NAV + holdings analysis.",
    SecurityType.ROYALTY_TRUST:  "Use commodity-price-linked DCF on the underlying reserves.",
}


# ============================================================
# Public API
# ============================================================
def classify_security(
    ticker: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    name: Optional[str] = None,
) -> SecurityClassification:
    """Classify a ticker. Cheap (no network)."""
    t = (ticker or "").upper().strip()

    # 1. Known-ticker shortcuts (highest confidence)
    if t in KNOWN_UTILITIES:
        return SecurityClassification(
            SecurityType.UTILITY, 1.0,
            f"{t} is a regulated utility on the known-shortlist.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.UTILITY],
        )
    if t in KNOWN_REITS:
        return SecurityClassification(
            SecurityType.REIT, 1.0,
            f"{t} is a REIT on the known-shortlist.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.REIT],
        )
    if t in KNOWN_BANKS:
        return SecurityClassification(
            SecurityType.BANK, 1.0,
            f"{t} is a major bank on the known-shortlist.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.BANK],
        )
    if t in KNOWN_INSURERS:
        return SecurityClassification(
            SecurityType.INSURANCE, 1.0,
            f"{t} is an insurer on the known-shortlist.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.INSURANCE],
        )
    if t in KNOWN_BDCS:
        return SecurityClassification(
            SecurityType.BDC, 1.0,
            f"{t} is a Business Development Company.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.BDC],
        )
    if t in KNOWN_MLPS:
        return SecurityClassification(
            SecurityType.MLP, 1.0,
            f"{t} is a Master Limited Partnership.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.MLP],
        )
    if t in KNOWN_ROYALTY_TRUSTS:
        return SecurityClassification(
            SecurityType.ROYALTY_TRUST, 1.0,
            f"{t} is a royalty trust.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.ROYALTY_TRUST],
        )
    if t in KNOWN_ETF_TICKERS:
        return SecurityClassification(
            SecurityType.FUND, 1.0,
            f"{t} is an ETF on the known-shortlist.",
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.FUND],
        )

    # 2. Name-based ETF detection (e.g. "Vanguard Total Stock Market ETF")
    if name and any(name.upper().rstrip(".").endswith(s)
                     for s in KNOWN_ETF_NAME_SUFFIXES):
        return SecurityClassification(
            SecurityType.FUND, 0.85,
            f'Name "{name}" suggests a fund / ETF.',
            valuation_applicable=False,
            suggested_alternative=_ALTERNATIVES[SecurityType.FUND],
        )

    # 3. Sector → type mapping (clear cases only)
    if sector:
        st = _SECTOR_TO_TYPE.get(sector)
        if st is not None:
            return SecurityClassification(
                st, 0.95,
                f'Sector "{sector}" → {st.value}.',
                valuation_applicable=False,
                suggested_alternative=_ALTERNATIVES.get(st),
            )

    # 4. Industry-keyword search
    if industry:
        ind_lower = industry.lower()
        for keyword, st in _INDUSTRY_KEYWORDS:
            if keyword.lower() in ind_lower:
                return SecurityClassification(
                    st, 0.85,
                    f'Industry contains "{keyword}".',
                    valuation_applicable=False,
                    suggested_alternative=_ALTERNATIVES.get(st),
                )

    # 5. Default — operating company
    return SecurityClassification(
        SecurityType.OPERATING, 0.70,
        "No specialised classification — treating as operating company.",
        valuation_applicable=True,
    )


def is_operating_company(
    ticker: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    name: Optional[str] = None,
) -> bool:
    """Convenience: True iff the FCFF DCF applies cleanly."""
    return classify_security(ticker, sector, industry, name).valuation_applicable
