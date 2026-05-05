"""
Curated ticker lists exposed on the Equity Analysis landing page.

Hand-picked because the alternative — running a live screener against a
500-ticker universe on every landing render — is too slow for what is
essentially a "suggestions" widget. Refresh manually as the universe
drifts.
"""
from __future__ import annotations


# ============================================================
# Lists
# ============================================================
SP500_LEADERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
    "BRK-B", "LLY", "TSLA", "AVGO",
)

# Low historical P/E + decent ROE — names that screen as "value"
VALUE_PICKS: tuple[str, ...] = (
    "JPM", "BAC", "WFC", "C", "GS",          # Big-cap financials
    "XOM", "CVX", "COP",                     # Integrated energy
    "T", "VZ",                               # Telco
    "INTC",                                  # Semis turnaround
)

# High-growth — usually trade at premium multiples
GROWTH_STOCKS: tuple[str, ...] = (
    "NVDA", "TSLA", "META", "PLTR",
    "CRM", "NOW", "AMD", "AVGO",
    "ABNB", "INTU",
)

# Companies with ≥25 years of consecutive dividend increases (the
# "Dividend Aristocrats" subset that overlaps our curated universe)
DIVIDEND_CHAMPIONS: tuple[str, ...] = (
    "KO", "PEP", "PG", "JNJ", "MCD",
    "WMT", "TGT", "MMM", "MO", "T",
    "CVX", "XOM",
)


# ============================================================
# Public API
# ============================================================
POPULAR_LISTS: dict[str, tuple[str, ...]] = {
    "S&P 500 leaders":   SP500_LEADERS,
    "Value picks":       VALUE_PICKS,
    "Growth stocks":     GROWTH_STOCKS,
    "Dividend champions": DIVIDEND_CHAMPIONS,
}


def get_list(name: str) -> tuple[str, ...]:
    """Lookup by display name; empty tuple if unknown."""
    return POPULAR_LISTS.get(name, ())
