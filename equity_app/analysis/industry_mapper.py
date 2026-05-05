"""
GICS-industry → Damodaran-industry name mapping.

Damodaran publishes ~99 industries on a custom taxonomy that doesn't
line up 1:1 with GICS. The dict below covers the slices most relevant
to our curated S&P 500 demo universe; tickers in industries we don't
map fall through to the broad "Total Market (without financials)"
benchmark so the UI never shows a missing comparison.

Refresh as Damodaran rebrands his categories (his column header naming
shifts most years; this map sits at the API boundary so the rest of the
app stays insulated).
"""
from __future__ import annotations
from typing import Optional


DAMODARAN_TO_GICS: dict[str, list[str]] = {
    # ---- Technology ----
    "Software (Internet)":              ["Internet Content & Information",
                                          "Internet Retail"],
    "Software (System & Application)":  ["Software—Application",
                                          "Software — Application",
                                          "Software—Infrastructure",
                                          "Software — Infrastructure"],
    "Computers/Peripherals":            ["Consumer Electronics",
                                          "Computer Hardware"],
    "Semiconductor":                    ["Semiconductors",
                                          "Semiconductor Equipment & Materials"],
    "Telecom (Wireless)":               ["Telecom Services"],
    "Telecom Services":                 ["Telecom Services"],

    # ---- Healthcare ----
    "Healthcare Products":              ["Medical Devices",
                                          "Medical Instruments & Supplies"],
    "Healthcare Information & Tech":    ["Health Information Services"],
    "Healthcare Support Services":      ["Healthcare Plans"],
    "Drugs (Pharmaceutical)":           ["Drug Manufacturers—General",
                                          "Drug Manufacturers — General",
                                          "Drug Manufacturers—Specialty & Generic",
                                          "Drug Manufacturers — Specialty & Generic"],
    "Drugs (Biotechnology)":            ["Biotechnology"],

    # ---- Financials ----
    "Banks (Money Center)":             ["Banks—Diversified",
                                          "Banks — Diversified",
                                          "Banks - Diversified"],
    "Banks (Regional)":                 ["Banks—Regional",
                                          "Banks — Regional"],
    "Brokerage & Investment Banking":   ["Capital Markets"],
    "Insurance (General)":              ["Insurance—Diversified"],
    "Investments & Asset Management":   ["Asset Management"],

    # ---- Consumer ----
    "Retail (General)":                 ["Department Stores",
                                          "Discount Stores"],
    "Retail (Online)":                  ["Internet Retail"],
    "Retail (Special Lines)":           ["Specialty Retail"],
    "Restaurant/Dining":                ["Restaurants"],
    "Beverage (Soft)":                  ["Beverages — Non-Alcoholic"],
    "Beverage (Alcoholic)":             ["Beverages — Brewers",
                                          "Beverages — Wineries & Distilleries"],
    "Food Wholesalers":                 ["Food Distribution"],
    "Household Products":               ["Household & Personal Products"],
    "Tobacco":                          ["Tobacco"],
    "Apparel":                          ["Apparel Manufacturing",
                                          "Apparel Retail"],
    "Auto & Truck":                     ["Auto Manufacturers"],
    "Auto Parts":                       ["Auto Parts"],

    # ---- Industrials / energy / materials ----
    "Aerospace/Defense":                ["Aerospace & Defense"],
    "Engineering/Construction":         ["Engineering & Construction"],
    "Heavy Construction":               ["Engineering & Construction"],
    "Machinery":                        ["Farm & Heavy Construction Machinery",
                                          "Specialty Industrial Machinery"],
    "Air Transport":                    ["Airlines"],
    "Trucking":                         ["Trucking"],
    "Transportation":                   ["Integrated Freight & Logistics"],
    "Oil/Gas (Integrated)":             ["Oil & Gas Integrated"],
    "Oil/Gas (Production and Exploration)": ["Oil & Gas E&P"],
    "Oilfield Services/Equipment":      ["Oil & Gas Equipment & Services"],
    "Coal & Related Energy":            ["Thermal Coal"],

    # ---- Utilities ----
    "Utility (General)":                ["Utilities — Regulated Electric",
                                          "Utilities — Regulated Gas",
                                          "Utilities — Diversified"],
    "Utility (Water)":                  ["Utilities — Regulated Water"],
    "Power":                            ["Utilities — Independent Power Producers"],

    # ---- Materials ----
    "Chemical (Basic)":                 ["Chemicals"],
    "Chemical (Specialty)":             ["Specialty Chemicals"],
    "Metals & Mining":                  ["Other Industrial Metals & Mining",
                                          "Other Precious Metals & Mining"],
    "Steel":                            ["Steel"],
    "Building Materials":               ["Building Materials"],
    "Paper/Forest Products":            ["Paper & Paper Products"],

    # ---- Real estate ----
    "R.E.I.T.":                         ["REIT — Diversified",
                                          "REIT — Industrial",
                                          "REIT — Office",
                                          "REIT — Residential",
                                          "REIT — Retail",
                                          "REIT — Specialty"],
    "Real Estate (Operations & Services)": ["Real Estate Services"],
}

# Reverse index: GICS-industry → damodaran-industry (first match wins).
_GICS_TO_DAMODARAN: dict[str, str] = {}
for damodaran, gics_list in DAMODARAN_TO_GICS.items():
    for g in gics_list:
        _GICS_TO_DAMODARAN.setdefault(g, damodaran)

# Sector-level fallbacks when the specific GICS industry isn't mapped.
SECTOR_FALLBACK: dict[str, str] = {
    "Technology":             "Software (System & Application)",
    "Healthcare":             "Drugs (Pharmaceutical)",
    "Financial Services":     "Banks (Money Center)",
    "Financials":             "Banks (Money Center)",
    "Consumer Discretionary": "Retail (General)",
    "Consumer Staples":       "Household Products",
    "Communication Services": "Telecom Services",
    "Industrials":            "Machinery",
    "Energy":                 "Oil/Gas (Integrated)",
    "Utilities":              "Utility (General)",
    "Materials":              "Chemical (Basic)",
    "Real Estate":            "R.E.I.T.",
}

DEFAULT_FALLBACK = "Total Market (without financials)"


def get_damodaran_industry(
    gics_industry: Optional[str],
    *,
    sector: Optional[str] = None,
) -> str:
    """
    Resolve a GICS industry name (or sector when industry is missing)
    to the closest Damodaran category. Always returns a non-empty
    string — falls back to the broad-market category when nothing
    matches.
    """
    if gics_industry and gics_industry in _GICS_TO_DAMODARAN:
        return _GICS_TO_DAMODARAN[gics_industry]
    if sector and sector in SECTOR_FALLBACK:
        return SECTOR_FALLBACK[sector]
    return DEFAULT_FALLBACK
