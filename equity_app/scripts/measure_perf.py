"""
Quick page-load performance smoke test.

Runs each Streamlit page through ``streamlit.testing.v1.AppTest`` and
reports total load time + error / warning count. Use as a regression
check before / after performance work.

Usage:

    cd equity_app && python scripts/measure_perf.py
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
import warnings


def measure_page_load(page_path: str, ticker: str = "AAPL") -> dict:
    warnings.filterwarnings("ignore")
    from streamlit.testing.v1 import AppTest

    t0 = time.time()
    at = AppTest.from_file(page_path, default_timeout=120)
    if "Equity_Analysis" in page_path:
        at.session_state["eq_active_ticker"] = ticker
    elif "Portfolio_Optimizer" in page_path:
        at.session_state["po_loaded"] = True
        at.session_state["portfolio_prefill"] = {
            "tickers":   "AAPL,MSFT,GOOGL,NVDA,AMZN",
            "objective": "Max Sharpe",
            "years":     5,
        }
    at.run()
    elapsed = time.time() - t0

    return {
        "page":         Path(page_path).name,
        "ticker":       ticker,
        "load_time_s":  elapsed,
        "exceptions":   len(at.exception),
        "errors":       len(at.error),
        "warnings":     len(at.warning),
        "tabs":         len(at.tabs),
        "metrics":      len(at.metric),
    }


def main() -> None:
    os.environ.setdefault("SEC_USER_AGENT", "perf claude.ai/code test@example.com")
    root = Path(__file__).resolve().parent.parent
    pages = [
        root / "pages" / "0_📊_Markets.py",
        root / "pages" / "1_🔎_Equity_Analysis.py",
        root / "pages" / "2_📈_Portfolio_Optimizer.py",
        root / "pages" / "3_🌐_Macro.py",
    ]
    print(f"{'Page':<40s}  {'Load':>7s}  {'Tabs':>5s}  {'Metrics':>7s}  {'Errors'}")
    print("-" * 80)
    for p in pages:
        if not p.exists():
            print(f"{p.name:<40s}  MISSING")
            continue
        r = measure_page_load(str(p))
        print(
            f"{r['page']:<40s}  {r['load_time_s']:6.2f}s  "
            f"{r['tabs']:>5d}  {r['metrics']:>7d}  "
            f"{r['exceptions']} excs / {r['errors']} errs"
        )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
