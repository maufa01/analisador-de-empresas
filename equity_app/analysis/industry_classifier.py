"""
Normalize provider sector / industry strings into the buckets the
valuation pipeline cares about.

The FCFF DCF only applies cleanly to non-financial companies. Banks,
insurers, and REITs all need different valuation engines:
- Banks: Residual Income or Dividend Discount
- Insurers: Embedded Value or DDM
- REITs: FFO / AFFO multiples

We classify by matching the provider sector / industry strings against
keyword sets. Robust to naming drift across yfinance / FMP / SEC.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# Keyword sets — case-insensitive substring match. Order doesn't matter;
# we test every category before returning so a single ticker can flag in
# multiple categories (e.g. an insurer that's also a financial holding).
_BANK_KEYWORDS = {
    "bank", "banking",
}
_INSURANCE_KEYWORDS = {
    "insurance", "insurers", "reinsurance",
}
_REIT_KEYWORDS = {
    "reit", "real estate investment trust",
}
_BROKER_KEYWORDS = {
    "capital markets", "brokerage", "investment banking",
}
_ASSET_MGMT_KEYWORDS = {
    "asset management", "investment management",
}

# Hard-coded ticker overrides — for cases where sector strings are
# ambiguous (e.g. a bank classified as "Financial Services" without
# more detail). Add sparingly; the keyword path should cover most.
_BANK_TICKERS = {
    "JPM", "BAC", "WFC", "C", "GS", "MS",
    "USB", "TFC", "PNC", "COF", "SCHW", "BK", "STT",
}
_INSURANCE_TICKERS = {
    "BRK.B", "BRK-B", "BRK.A", "BRK-A",
    "PGR", "TRV", "AIG", "ALL", "MET", "PRU", "AFL",
    "CB", "HIG", "L", "RGA",
}
_REIT_TICKERS = {
    "AMT", "PLD", "EQIX", "CCI", "PSA", "O", "WELL",
    "DLR", "SPG", "VICI", "AVB", "EQR", "EXR", "ARE",
}


@dataclass(frozen=True)
class IndustryClassification:
    ticker: str
    sector: Optional[str]
    industry: Optional[str]
    is_bank: bool
    is_insurance: bool
    is_reit: bool
    is_broker: bool
    is_asset_manager: bool

    @property
    def is_financial(self) -> bool:
        return any((self.is_bank, self.is_insurance, self.is_broker,
                    self.is_asset_manager))


def _matches_any(text: Optional[str], keywords: set[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in keywords)


def classify_industry(
    ticker: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> IndustryClassification:
    """Classify a ticker into the valuation-pipeline categories.

    All flags can be False — that's a "normal" industrial / consumer /
    tech company that the FCFF DCF handles cleanly.
    """
    t = (ticker or "").upper().strip()

    # Combined string — keyword search hits either sector or industry
    bag = " ".join(filter(None, [sector, industry])) or ""

    is_bank = (
        t in _BANK_TICKERS
        or _matches_any(bag, _BANK_KEYWORDS)
    )
    is_insurance = (
        t in _INSURANCE_TICKERS
        or _matches_any(bag, _INSURANCE_KEYWORDS)
    )
    is_reit = (
        t in _REIT_TICKERS
        or _matches_any(bag, _REIT_KEYWORDS)
        or _matches_any(sector, {"real estate"})
    )
    is_broker = _matches_any(bag, _BROKER_KEYWORDS)
    is_asset_manager = _matches_any(bag, _ASSET_MGMT_KEYWORDS)

    return IndustryClassification(
        ticker=t, sector=sector, industry=industry,
        is_bank=is_bank, is_insurance=is_insurance, is_reit=is_reit,
        is_broker=is_broker, is_asset_manager=is_asset_manager,
    )


# ============================================================
# Business-profile classifier — used by the valuation aggregator to
# pick the right weighted average across DCF / EPV / Multiples / etc.
# ============================================================
_GROWTH_TECH_KEYWORDS = ("technology", "communication", "information technology")
_CYCLICAL_KEYWORDS = ("energy", "materials", "industrials",
                       "consumer cyclical", "consumer discretionary",
                       "basic materials")
_DIVIDEND_PAYER_KEYWORDS = ("utilities",)
_STEADY_KEYWORDS = ("consumer staples", "consumer defensive", "healthcare")


def classify_business_profile(
    ticker: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> str:
    """Return one of:
       bank | insurance | reit | steady_compounder | growth_tech
       | cyclical | dividend_payer | default

    Financials override sector: a bank classified as "Financial Services"
    still returns "bank" so the aggregator picks Residual-Income-heavy
    weights instead of the DCF-heavy default.
    """
    cls = classify_industry(ticker, sector, industry)
    if cls.is_bank:
        return "bank"
    if cls.is_insurance:
        return "insurance"
    if cls.is_reit:
        return "reit"

    s = (sector or "").lower()
    if any(k in s for k in _GROWTH_TECH_KEYWORDS):
        return "growth_tech"
    if any(k in s for k in _DIVIDEND_PAYER_KEYWORDS):
        return "dividend_payer"
    if any(k in s for k in _STEADY_KEYWORDS):
        return "steady_compounder"
    if any(k in s for k in _CYCLICAL_KEYWORDS):
        return "cyclical"
    return "default"
