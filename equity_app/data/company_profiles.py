"""
Hardcoded company profiles, executives lists, and industry average
ratios — sufficient for the demo (AAPL / MSFT / JPM) until the live
FMP provider's ``get_company_profile`` / ``get_executives`` / industry-
average endpoints are wired in.

Tickers outside the demo set fall through to ``None`` returns; the UI
components render a "data unavailable" placeholder.

Industry averages cover the ratio set that the Ratios tab displays.
Sources: company 10-Ks (FY2023), Damodaran's industry tables for
US Sector data, and recent CFA-Institute / NYU benchmarks. Refresh
manually as the data drifts.
"""
from __future__ import annotations
from typing import Optional


# ============================================================
# Executives + profiles
# ============================================================
PROFILES: dict[str, dict] = {
    "AAPL": {
        "name": "Apple Inc.",
        "description": (
            "Apple Inc. designs, manufactures, and markets smartphones, "
            "personal computers, tablets, wearables, and accessories "
            "worldwide. The company also sells various services including "
            "the App Store, Apple Music, iCloud, Apple TV+, AppleCare and "
            "advertising. Founded in 1976 and headquartered in Cupertino, "
            "California."
        ),
        "ceo":            "Tim Cook",
        "ceo_since":      2011,
        "cfo":            "Luca Maestri",
        "founded":        "April 1, 1976",
        "headquarters":   "Cupertino, California",
        "employees":      164_000,
        "website":        "apple.com",
        "exchange":       "NASDAQ",
        "sector":         "Technology",
        "industry":       "Consumer Electronics",
        "fiscal_year_end": "September",
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "description": (
            "Microsoft Corporation develops, licenses, and supports software, "
            "services, devices, and solutions worldwide. The company operates "
            "in three segments: Productivity and Business Processes; "
            "Intelligent Cloud (Azure); and More Personal Computing. "
            "Founded in 1975 and headquartered in Redmond, Washington."
        ),
        "ceo":            "Satya Nadella",
        "ceo_since":      2014,
        "cfo":            "Amy Hood",
        "founded":        "April 4, 1975",
        "headquarters":   "Redmond, Washington",
        "employees":      221_000,
        "website":        "microsoft.com",
        "exchange":       "NASDAQ",
        "sector":         "Technology",
        "industry":       "Software — Infrastructure",
        "fiscal_year_end": "June",
    },
    "JPM": {
        "name": "JPMorgan Chase & Co.",
        "description": (
            "JPMorgan Chase & Co. operates as a financial services company "
            "worldwide. The company operates in four segments: Consumer & "
            "Community Banking, Corporate & Investment Bank, Commercial "
            "Banking, and Asset & Wealth Management. Founded in 1799 and "
            "headquartered in New York City."
        ),
        "ceo":            "Jamie Dimon",
        "ceo_since":      2005,
        "cfo":            "Jeremy Barnum",
        "founded":        "1799",
        "headquarters":   "New York City, New York",
        "employees":      316_000,
        "website":        "jpmorganchase.com",
        "exchange":       "NYSE",
        "sector":         "Financial Services",
        "industry":       "Banks — Diversified",
        "fiscal_year_end": "December",
    },
}


EXECUTIVES: dict[str, list[dict]] = {
    "AAPL": [
        {"name": "Tim Cook",        "role": "CEO",                          "since": 2011},
        {"name": "Luca Maestri",    "role": "CFO",                          "since": 2014},
        {"name": "Jeff Williams",   "role": "COO",                          "since": 2015},
        {"name": "Katherine Adams", "role": "General Counsel",              "since": 2017},
        {"name": "Deirdre O'Brien", "role": "SVP Retail + People",          "since": 2019},
        {"name": "Greg Joswiak",    "role": "SVP Worldwide Marketing",      "since": 2020},
    ],
    "MSFT": [
        {"name": "Satya Nadella",   "role": "Chairman & CEO",               "since": 2014},
        {"name": "Amy Hood",        "role": "CFO",                          "since": 2013},
        {"name": "Brad Smith",      "role": "Vice Chair & President",       "since": 2021},
        {"name": "Judson Althoff",  "role": "EVP Commercial Business",      "since": 2021},
        {"name": "Scott Guthrie",   "role": "EVP Cloud + AI Group",         "since": 2014},
        {"name": "Rajesh Jha",      "role": "EVP Experiences + Devices",    "since": 2018},
    ],
    "JPM": [
        {"name": "Jamie Dimon",     "role": "Chairman & CEO",               "since": 2005},
        {"name": "Daniel Pinto",    "role": "President & COO",              "since": 2022},
        {"name": "Jeremy Barnum",   "role": "CFO",                          "since": 2021},
        {"name": "Mary Erdoes",     "role": "CEO Asset & Wealth Mgmt",      "since": 2009},
        {"name": "Marianne Lake",   "role": "CEO Consumer & Comm Banking",  "since": 2024},
        {"name": "Doug Petno",      "role": "CEO Commercial Banking",       "since": 2012},
    ],
}


# ============================================================
# Industry-average ratios (used by the Ratios tab cards)
# ============================================================
INDUSTRY_AVERAGES: dict[str, dict[str, float]] = {
    # ---- Tech / consumer electronics + software ----
    "Technology": {
        "gross_margin":      38.2,
        "operating_margin":  18.9,
        "ebitda_margin":     22.5,
        "net_margin":        15.6,
        "fcf_margin":        18.0,
        "roe":               32.1,
        "roa":               12.5,
        "roic":              22.3,
        "asset_turnover":    0.85,
        "current_ratio":     1.85,
        "quick_ratio":       1.55,
        "cash_ratio":        0.95,
        "debt_to_equity":    0.65,
        "debt_to_ebitda":    1.40,
        "interest_coverage": 22.0,
        "pe_ratio":          27.4,
        "forward_pe":        25.0,
        "ev_ebitda":         19.0,
        "ps_ratio":          5.20,
        "pb_ratio":          7.10,
    },
    # ---- Big banks ----
    "Financial Services": {
        "gross_margin":      None,           # Banks don't report a meaningful "gross margin"
        "operating_margin":  35.5,
        "ebitda_margin":     None,
        "net_margin":        24.0,
        "fcf_margin":        None,
        "roe":               12.0,
        "roa":               1.10,
        "roic":              8.5,
        "asset_turnover":    0.05,
        "current_ratio":     None,           # Inappropriate for a bank
        "quick_ratio":       None,
        "cash_ratio":        None,
        "debt_to_equity":    1.50,
        "debt_to_ebitda":    None,
        "interest_coverage": 4.0,
        "pe_ratio":          11.0,
        "forward_pe":        10.5,
        "ev_ebitda":         None,
        "ps_ratio":          2.40,
        "pb_ratio":          1.40,
    },
}


# ============================================================
# Public API — returns None for unknown tickers / sectors
# ============================================================
def get_company_profile(ticker: str) -> Optional[dict]:
    """Return the hardcoded profile dict, or None when the ticker is
    outside the curated demo set."""
    return PROFILES.get(ticker.upper())


def get_executives(ticker: str) -> list[dict]:
    """Top executives — empty list when not curated."""
    return EXECUTIVES.get(ticker.upper(), [])


def get_industry_averages(sector: Optional[str]) -> dict[str, Optional[float]]:
    """Industry-average ratios for a sector — empty dict if not curated."""
    if not sector:
        return {}
    return INDUSTRY_AVERAGES.get(sector, {})
