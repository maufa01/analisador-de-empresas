"""
Curated index constituents with GICS sector tags.

The full S&P 500 / Russell 2000 universes are too heavy to batch-fetch
on every page render (yfinance enforces implicit rate limits and 2000
tickers takes 30s+). Instead we ship a hand-picked S&P 500 mega/large-cap
subset of ~120 tickers that covers every GICS sector and is enough for
the demo movers tables.

Each entry is ``(ticker, name, GICS_SECTOR)``. Ticker → metadata lookups
are exposed via ``META`` and ``UNIVERSES``.

Adding a ticker: append to ``_RAW_SP500`` with the right sector — the
indexes are derived automatically.
"""
from __future__ import annotations

# ============================================================
# GICS sectors (canonical labels used across the page filters)
# ============================================================
SECTORS: tuple[str, ...] = (
    "Technology",
    "Healthcare",
    "Financials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Communication Services",
    "Industrials",
    "Energy",
    "Utilities",
    "Materials",
    "Real Estate",
)

# Sector → SPDR sector ETF (used by the heatmap as a proxy for sector return)
SECTOR_ETFS: dict[str, str] = {
    "Technology":             "XLK",
    "Healthcare":             "XLV",
    "Financials":             "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Communication Services": "XLC",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Utilities":              "XLU",
    "Materials":              "XLB",
    "Real Estate":            "XLRE",
}


# ============================================================
# Raw S&P 500 mega/large-cap subset (≈ 120 names across all 11 sectors)
# ============================================================
_RAW_SP500: list[tuple[str, str, str]] = [
    # ---------- Technology ----------
    ("AAPL",  "Apple Inc.",                       "Technology"),
    ("MSFT",  "Microsoft Corp.",                  "Technology"),
    ("NVDA",  "NVIDIA Corp.",                     "Technology"),
    ("AVGO",  "Broadcom Inc.",                    "Technology"),
    ("ORCL",  "Oracle Corp.",                     "Technology"),
    ("CRM",   "Salesforce Inc.",                  "Technology"),
    ("ADBE",  "Adobe Inc.",                       "Technology"),
    ("CSCO",  "Cisco Systems Inc.",               "Technology"),
    ("AMD",   "Advanced Micro Devices",           "Technology"),
    ("INTC",  "Intel Corp.",                      "Technology"),
    ("QCOM",  "Qualcomm Inc.",                    "Technology"),
    ("TXN",   "Texas Instruments",                "Technology"),
    ("IBM",   "IBM Corp.",                        "Technology"),
    ("INTU",  "Intuit Inc.",                      "Technology"),
    ("NOW",   "ServiceNow Inc.",                  "Technology"),
    ("PLTR",  "Palantir Technologies",            "Technology"),
    ("AMAT",  "Applied Materials",                "Technology"),
    ("MU",    "Micron Technology",                "Technology"),

    # ---------- Healthcare ----------
    ("LLY",   "Eli Lilly & Co.",                  "Healthcare"),
    ("UNH",   "UnitedHealth Group",               "Healthcare"),
    ("JNJ",   "Johnson & Johnson",                "Healthcare"),
    ("ABBV",  "AbbVie Inc.",                      "Healthcare"),
    ("MRK",   "Merck & Co.",                      "Healthcare"),
    ("PFE",   "Pfizer Inc.",                      "Healthcare"),
    ("TMO",   "Thermo Fisher Scientific",         "Healthcare"),
    ("ABT",   "Abbott Laboratories",              "Healthcare"),
    ("DHR",   "Danaher Corp.",                    "Healthcare"),
    ("BMY",   "Bristol-Myers Squibb",             "Healthcare"),
    ("AMGN",  "Amgen Inc.",                       "Healthcare"),
    ("CVS",   "CVS Health Corp.",                 "Healthcare"),
    ("GILD",  "Gilead Sciences",                  "Healthcare"),
    ("ISRG",  "Intuitive Surgical",               "Healthcare"),
    ("VRTX",  "Vertex Pharmaceuticals",           "Healthcare"),
    ("REGN",  "Regeneron Pharmaceuticals",        "Healthcare"),

    # ---------- Financials ----------
    ("BRK-B", "Berkshire Hathaway",               "Financials"),
    ("JPM",   "JPMorgan Chase & Co.",             "Financials"),
    ("V",     "Visa Inc.",                        "Financials"),
    ("MA",    "Mastercard Inc.",                  "Financials"),
    ("BAC",   "Bank of America",                  "Financials"),
    ("WFC",   "Wells Fargo & Co.",                "Financials"),
    ("GS",    "Goldman Sachs Group",              "Financials"),
    ("MS",    "Morgan Stanley",                   "Financials"),
    ("C",     "Citigroup Inc.",                   "Financials"),
    ("AXP",   "American Express",                 "Financials"),
    ("BLK",   "BlackRock Inc.",                   "Financials"),
    ("SCHW",  "Charles Schwab",                   "Financials"),
    ("PYPL",  "PayPal Holdings",                  "Financials"),
    ("PNC",   "PNC Financial Services",           "Financials"),
    ("USB",   "U.S. Bancorp",                     "Financials"),

    # ---------- Consumer Discretionary ----------
    ("AMZN",  "Amazon.com Inc.",                  "Consumer Discretionary"),
    ("TSLA",  "Tesla Inc.",                       "Consumer Discretionary"),
    ("HD",    "Home Depot Inc.",                  "Consumer Discretionary"),
    ("MCD",   "McDonald's Corp.",                 "Consumer Discretionary"),
    ("NKE",   "Nike Inc.",                        "Consumer Discretionary"),
    ("LOW",   "Lowe's Companies",                 "Consumer Discretionary"),
    ("SBUX",  "Starbucks Corp.",                  "Consumer Discretionary"),
    ("BKNG",  "Booking Holdings",                 "Consumer Discretionary"),
    ("TJX",   "TJX Companies",                    "Consumer Discretionary"),
    ("MAR",   "Marriott International",           "Consumer Discretionary"),
    ("F",     "Ford Motor Company",               "Consumer Discretionary"),
    ("GM",    "General Motors",                   "Consumer Discretionary"),
    ("ABNB",  "Airbnb Inc.",                      "Consumer Discretionary"),

    # ---------- Consumer Staples ----------
    ("WMT",   "Walmart Inc.",                     "Consumer Staples"),
    ("PG",    "Procter & Gamble",                 "Consumer Staples"),
    ("KO",    "Coca-Cola Co.",                    "Consumer Staples"),
    ("PEP",   "PepsiCo Inc.",                     "Consumer Staples"),
    ("COST",  "Costco Wholesale",                 "Consumer Staples"),
    ("MO",    "Altria Group",                     "Consumer Staples"),
    ("PM",    "Philip Morris International",      "Consumer Staples"),
    ("MDLZ",  "Mondelez International",           "Consumer Staples"),
    ("CL",    "Colgate-Palmolive",                "Consumer Staples"),
    ("KMB",   "Kimberly-Clark",                   "Consumer Staples"),
    ("TGT",   "Target Corp.",                     "Consumer Staples"),

    # ---------- Communication Services ----------
    ("GOOGL", "Alphabet Inc. (Class A)",          "Communication Services"),
    ("GOOG",  "Alphabet Inc. (Class C)",          "Communication Services"),
    ("META",  "Meta Platforms Inc.",              "Communication Services"),
    ("NFLX",  "Netflix Inc.",                     "Communication Services"),
    ("DIS",   "Walt Disney Co.",                  "Communication Services"),
    ("CMCSA", "Comcast Corp.",                    "Communication Services"),
    ("T",     "AT&T Inc.",                        "Communication Services"),
    ("VZ",    "Verizon Communications",           "Communication Services"),
    ("TMUS",  "T-Mobile US",                      "Communication Services"),

    # ---------- Industrials ----------
    ("GE",    "General Electric",                 "Industrials"),
    ("HON",   "Honeywell International",          "Industrials"),
    ("BA",    "Boeing Co.",                       "Industrials"),
    ("CAT",   "Caterpillar Inc.",                 "Industrials"),
    ("DE",    "Deere & Co.",                      "Industrials"),
    ("RTX",   "RTX Corp.",                        "Industrials"),
    ("LMT",   "Lockheed Martin",                  "Industrials"),
    ("UPS",   "United Parcel Service",            "Industrials"),
    ("FDX",   "FedEx Corp.",                      "Industrials"),
    ("UNP",   "Union Pacific",                    "Industrials"),
    ("MMM",   "3M Co.",                           "Industrials"),

    # ---------- Energy ----------
    ("XOM",   "Exxon Mobil",                      "Energy"),
    ("CVX",   "Chevron Corp.",                    "Energy"),
    ("COP",   "ConocoPhillips",                   "Energy"),
    ("SLB",   "Schlumberger NV",                  "Energy"),
    ("EOG",   "EOG Resources",                    "Energy"),
    ("PSX",   "Phillips 66",                      "Energy"),
    ("MPC",   "Marathon Petroleum",               "Energy"),
    ("OXY",   "Occidental Petroleum",             "Energy"),

    # ---------- Utilities ----------
    ("NEE",   "NextEra Energy",                   "Utilities"),
    ("DUK",   "Duke Energy",                      "Utilities"),
    ("SO",    "Southern Co.",                     "Utilities"),
    ("D",     "Dominion Energy",                  "Utilities"),
    ("AEP",   "American Electric Power",          "Utilities"),
    ("EXC",   "Exelon Corp.",                     "Utilities"),

    # ---------- Materials ----------
    ("LIN",   "Linde plc",                        "Materials"),
    ("FCX",   "Freeport-McMoRan",                 "Materials"),
    ("NEM",   "Newmont Corp.",                    "Materials"),
    ("DOW",   "Dow Inc.",                         "Materials"),
    ("DD",    "DuPont de Nemours",                "Materials"),
    ("APD",   "Air Products & Chemicals",         "Materials"),

    # ---------- Real Estate ----------
    ("AMT",   "American Tower",                   "Real Estate"),
    ("PLD",   "Prologis Inc.",                    "Real Estate"),
    ("EQIX",  "Equinix Inc.",                     "Real Estate"),
    ("CCI",   "Crown Castle",                     "Real Estate"),
    ("PSA",   "Public Storage",                   "Real Estate"),
    ("WELL",  "Welltower Inc.",                   "Real Estate"),
]


# ============================================================
# Derived indices
# ============================================================
META: dict[str, dict[str, str]] = {
    t: {"name": n, "sector": s} for (t, n, s) in _RAW_SP500
}

# Build sector → tickers map for fast filtering
_BY_SECTOR: dict[str, list[str]] = {s: [] for s in SECTORS}
for t, _, s in _RAW_SP500:
    if s in _BY_SECTOR:
        _BY_SECTOR[s].append(t)


# ============================================================
# Pre-defined universe slices
# ============================================================
# Dow 30 — official members
DOW_30: tuple[str, ...] = (
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD",
    "MMM", "MRK", "MSFT", "NKE", "PG", "TRV", "UNH", "V", "VZ", "WMT",
)

# Nasdaq 100 — top names from our universe that trade on Nasdaq
NASDAQ_100: tuple[str, ...] = tuple(t for t, _, _ in _RAW_SP500 if t in {
    "AAPL", "ABNB", "ADBE", "AMAT", "AMD", "AMGN", "AMZN", "AVGO",
    "BKNG", "CMCSA", "COST", "CRM", "CSCO", "GILD", "GOOG", "GOOGL",
    "HON", "IBM", "INTC", "INTU", "ISRG", "LIN", "MAR", "META",
    "MDLZ", "MRK", "MSFT", "MU", "NFLX", "NVDA", "ORCL", "PEP",
    "PYPL", "QCOM", "REGN", "SBUX", "TMUS", "TSLA", "TXN", "VRTX",
})

SP500: tuple[str, ...] = tuple(t for t, _, _ in _RAW_SP500)

# Russell 2000 placeholder — too big to ship in a hardcoded list and
# yfinance can't batch-fetch 2000 names reliably. We expose the same
# S&P large-cap universe under this key so the UI can offer the option
# without breaking. Wire to a real provider in a later session.
RUSSELL_2000: tuple[str, ...] = SP500


UNIVERSES: dict[str, tuple[str, ...]] = {
    "S&P 500":      SP500,
    "Nasdaq 100":   NASDAQ_100,
    "Dow 30":       DOW_30,
    "Russell 2000": RUSSELL_2000,
}


# ============================================================
# Helpers
# ============================================================
def tickers_in(universe: str) -> list[str]:
    """Returns the ticker list for a universe key (case-insensitive)."""
    for key, vals in UNIVERSES.items():
        if key.lower() == universe.lower():
            return list(vals)
    return list(SP500)


def sector_of(ticker: str) -> str | None:
    """Returns the GICS sector for a ticker, or None if unknown."""
    return META.get(ticker.upper(), {}).get("sector")


def name_of(ticker: str) -> str:
    """Returns the company name for a ticker, falling back to the ticker."""
    return META.get(ticker.upper(), {}).get("name", ticker)


def tickers_by_sector(universe: str, sector: str) -> list[str]:
    """Subset of ``universe`` belonging to ``sector``."""
    pool = set(tickers_in(universe))
    return [t for t in _BY_SECTOR.get(sector, []) if t in pool]
