"""
Headless verification that loads 12 diverse tickers and checks none
trigger the bugs PROMPT 12 was meant to fix.

Run: python equity_app/scripts/verify_universal_fixes.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.parallel_loader import load_bundle
from analysis.security_classifier import classify_security, SecurityType
from analysis.ratios import calculate_ratios


# Ticker test matrix — diverse sectors and sizes
TEST_TICKERS = [
    # Operating companies (full analysis must succeed)
    ("AAPL", "Technology",         SecurityType.OPERATING),
    ("MSFT", "Technology",         SecurityType.OPERATING),
    ("NVDA", "Technology",         SecurityType.OPERATING),
    ("JNJ",  "Healthcare",         SecurityType.OPERATING),
    ("KO",   "Consumer Defensive", SecurityType.OPERATING),
    ("V",    "Financial Services", SecurityType.OPERATING),  # payment processor, not a bank
    ("CAT",  "Industrials",        SecurityType.OPERATING),
    ("XOM",  "Energy",             SecurityType.OPERATING),

    # Non-operating (must be soft-blocked with a clear reason)
    ("DUK",  "Utilities",          SecurityType.UTILITY),
    ("AMT",  "Real Estate",        SecurityType.REIT),
    ("JPM",  "Financial Services", SecurityType.BANK),
    ("SPY",  None,                 SecurityType.FUND),
]


def verify_ticker(ticker: str, expected_sector, expected_type: SecurityType) -> dict:
    """Return dict with bug-flag status for one ticker."""
    issues: list[str] = []

    try:
        bundle = load_bundle(ticker)
    except Exception as e:
        return {
            "ticker": ticker,
            "classification": "?",
            "valuation_applicable": "?",
            "n_peers": 0,
            "has_description": False,
            "issues": [f"LOAD_FAILED: {type(e).__name__}: {e}"],
        }

    # CHECK 1 — classification
    sec = classify_security(
        ticker,
        sector=(bundle.info or {}).get("sector"),
        industry=(bundle.info or {}).get("industry"),
        name=(bundle.info or {}).get("name"),
    )
    if sec.security_type != expected_type:
        issues.append(
            f"WRONG_CLASSIFICATION: got {sec.security_type.value}, expected {expected_type.value}"
        )

    # CHECK 2 — description present (operating-only — ETFs OK without)
    has_description = bool(
        (bundle.fmp_profile or {}).get("description")
        or (bundle.info or {}).get("longBusinessSummary")
        or (bundle.info or {}).get("description")
    )
    if not has_description and expected_type == SecurityType.OPERATING:
        issues.append("NO_DESCRIPTION (will show 'will populate' fallback)")

    # CHECK 3 — revenue healing worked (operating-only)
    if expected_type == SecurityType.OPERATING:
        if bundle.income is None or bundle.income.empty:
            issues.append("EMPTY_INCOME_STATEMENT")
        else:
            cols = bundle.income.columns
            rev_col = (
                "revenue" if "revenue" in cols
                else "totalRevenue" if "totalRevenue" in cols
                else None
            )
            if rev_col is None:
                issues.append("NO_REVENUE_COLUMN (heal failed)")
            else:
                rev = bundle.income[rev_col]
                if rev.dropna().empty:
                    issues.append("REVENUE_ALL_NAN")

    # CHECK 4 — ratios compute without exceptions. ETFs/funds don't have
    # income statements, so empty ratios for them is expected, not a bug.
    try:
        ratios = calculate_ratios(bundle.income, bundle.balance, bundle.cash)
        if expected_type == SecurityType.OPERATING:
            if ratios is None or ratios.empty:
                issues.append("RATIOS_EMPTY")
            elif "Net Margin %" not in ratios.columns:
                issues.append("NO_NET_MARGIN_COLUMN")
            else:
                last_nm = ratios["Net Margin %"].dropna().tail(1)
                if last_nm.empty:
                    issues.append("NET_MARGIN_ALL_NAN")
    except Exception as e:
        issues.append(f"RATIOS_RAISED: {type(e).__name__}: {e}")

    # CHECK 5 — peers resolved (operating + non-operating except ETFs)
    if expected_type != SecurityType.FUND:
        n = len(bundle.peers) if bundle.peers else 0
        if n == 0:
            issues.append("NO_PEERS_RESOLVED")
        elif n < 3:
            issues.append(f"FEW_PEERS ({n})")

    return {
        "ticker": ticker,
        "classification": sec.security_type.value,
        "valuation_applicable": sec.valuation_applicable,
        "n_peers": len(bundle.peers) if bundle.peers else 0,
        "has_description": has_description,
        "issues": issues,
    }


def main() -> int:
    header = f"{'TICKER':<8}{'CLASS':<14}{'VAL?':<7}{'PEERS':<7}{'DESC':<6}ISSUES"
    print(header)
    print("-" * 100)

    all_clean = True
    for ticker, sector, expected in TEST_TICKERS:
        r = verify_ticker(ticker, sector, expected)
        issues_str = "; ".join(r["issues"]) if r["issues"] else "OK"
        if r["issues"]:
            all_clean = False
        print(
            f"{r['ticker']:<8}"
            f"{r['classification']:<14}"
            f"{str(r['valuation_applicable']):<7}"
            f"{r['n_peers']:<7}"
            f"{('Y' if r['has_description'] else 'N'):<6}"
            f"{issues_str}"
        )
    print("-" * 100)
    if all_clean:
        print("✓ ALL TICKERS PASS")
        return 0
    print("✗ ISSUES DETECTED — fix before closing PR")
    return 1


if __name__ == "__main__":
    sys.exit(main())
