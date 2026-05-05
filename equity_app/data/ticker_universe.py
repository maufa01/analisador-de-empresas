"""
Curated ticker → company-name map for the search dropdowns.

Lives separately from ``market_data`` so multiple pages can share one
universe (Equity Analysis, future Compare/Watchlist) without circular
imports. Universe is the S&P 500 mega-/large-cap subset most users
care about — extend as needed; the FMP screener replaces this once the
live provider is wired in.

Each value is the human-readable name; the key is the yfinance/FMP
ticker. ``LABELS`` gives the pre-formatted "TICKER — Name" strings used
by ``st.selectbox`` (which is type-searchable out of the box).
"""
from __future__ import annotations


SP500_TOP: dict[str, str] = {
    # ---- Mega-cap technology / communication ----
    "AAPL":  "Apple Inc.",
    "MSFT":  "Microsoft Corp.",
    "GOOGL": "Alphabet Inc. (Class A)",
    "GOOG":  "Alphabet Inc. (Class C)",
    "AMZN":  "Amazon.com Inc.",
    "META":  "Meta Platforms Inc.",
    "NVDA":  "NVIDIA Corp.",
    "TSLA":  "Tesla Inc.",
    "AVGO":  "Broadcom Inc.",
    "ORCL":  "Oracle Corp.",
    "CRM":   "Salesforce Inc.",
    "ADBE":  "Adobe Inc.",
    "NFLX":  "Netflix Inc.",
    "CSCO":  "Cisco Systems Inc.",
    "AMD":   "Advanced Micro Devices",
    "INTC":  "Intel Corp.",
    "QCOM":  "Qualcomm Inc.",
    "TXN":   "Texas Instruments",
    "IBM":   "IBM Corp.",
    "INTU":  "Intuit Inc.",
    "NOW":   "ServiceNow Inc.",
    "PLTR":  "Palantir Technologies",
    "DIS":   "Walt Disney Co.",
    "CMCSA": "Comcast Corp.",
    "T":     "AT&T Inc.",
    "VZ":    "Verizon Communications",

    # ---- Financial services ----
    "BRK-B": "Berkshire Hathaway",
    "JPM":   "JPMorgan Chase & Co.",
    "V":     "Visa Inc.",
    "MA":    "Mastercard Inc.",
    "BAC":   "Bank of America",
    "WFC":   "Wells Fargo & Co.",
    "GS":    "Goldman Sachs Group",
    "MS":    "Morgan Stanley",
    "C":     "Citigroup Inc.",
    "AXP":   "American Express",
    "BLK":   "BlackRock Inc.",
    "SCHW":  "Charles Schwab",
    "PYPL":  "PayPal Holdings",

    # ---- Healthcare ----
    "LLY":   "Eli Lilly & Co.",
    "UNH":   "UnitedHealth Group",
    "JNJ":   "Johnson & Johnson",
    "ABBV":  "AbbVie Inc.",
    "MRK":   "Merck & Co.",
    "PFE":   "Pfizer Inc.",
    "TMO":   "Thermo Fisher Scientific",
    "ABT":   "Abbott Laboratories",
    "DHR":   "Danaher Corp.",
    "BMY":   "Bristol-Myers Squibb",
    "AMGN":  "Amgen Inc.",
    "CVS":   "CVS Health Corp.",
    "GILD":  "Gilead Sciences",
    "ISRG":  "Intuitive Surgical",
    "VRTX":  "Vertex Pharmaceuticals",
    "REGN":  "Regeneron Pharmaceuticals",

    # ---- Consumer staples / cyclical / retail ----
    "WMT":   "Walmart Inc.",
    "PG":    "Procter & Gamble",
    "KO":    "Coca-Cola Co.",
    "PEP":   "PepsiCo Inc.",
    "COST":  "Costco Wholesale",
    "MCD":   "McDonald's Corp.",
    "SBUX":  "Starbucks Corp.",
    "NKE":   "Nike Inc.",
    "HD":    "Home Depot Inc.",
    "LOW":   "Lowe's Companies",
    "TGT":   "Target Corp.",
    "BKNG":  "Booking Holdings",
    "MAR":   "Marriott International",
    "MO":    "Altria Group",
    "PM":    "Philip Morris International",
    "MDLZ":  "Mondelez International",

    # ---- Industrials / energy / materials ----
    "GE":    "General Electric",
    "HON":   "Honeywell International",
    "BA":    "Boeing Co.",
    "CAT":   "Caterpillar Inc.",
    "DE":    "Deere & Co.",
    "RTX":   "RTX Corp.",
    "LMT":   "Lockheed Martin",
    "UPS":   "United Parcel Service",
    "FDX":   "FedEx Corp.",
    "XOM":   "Exxon Mobil",
    "CVX":   "Chevron Corp.",
    "COP":   "ConocoPhillips",
    "SLB":   "Schlumberger NV",
    "EOG":   "EOG Resources",
    "LIN":   "Linde plc",
    "FCX":   "Freeport-McMoRan",
    "NEM":   "Newmont Corp.",

    # ---- Real estate / utilities ----
    "AMT":   "American Tower",
    "PLD":   "Prologis Inc.",
    "NEE":   "NextEra Energy",
    "DUK":   "Duke Energy",
    "SO":    "Southern Co.",

    # ---- ETFs commonly screened alongside ----
    "SPY":   "SPDR S&P 500 ETF",
    "QQQ":   "Invesco QQQ Trust",
    "DIA":   "SPDR Dow Jones ETF",
    "IWM":   "iShares Russell 2000 ETF",
    "VOO":   "Vanguard S&P 500 ETF",
    "VTI":   "Vanguard Total Stock Market",
    "GLD":   "SPDR Gold Trust",
    "TLT":   "iShares 20+ Year Treasury",
}


def labels(universe: dict[str, str] | None = None) -> list[str]:
    """``["AAPL — Apple Inc.", "MSFT — Microsoft Corp.", ...]`` for selectbox."""
    src = universe or SP500_TOP
    return [f"{t} — {n}" for t, n in src.items()]


def ticker_from_label(label: str) -> str:
    """Extract the bare ticker from a ``"TICKER — Name"`` label."""
    return label.split(" — ", 1)[0].strip().upper()
