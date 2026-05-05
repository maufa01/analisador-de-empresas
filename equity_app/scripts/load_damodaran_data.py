"""
One-shot ingestion of Damodaran's industry datasets into local parquet
files under ``data/damodaran/``. Run this once a year (Damodaran
publishes fresh data each January).

    cd equity_app
    python -m scripts.load_damodaran_data

The runtime ``analysis.damodaran_loader.get_industry_benchmarks`` reads
those parquets and falls back to the hardcoded averages in
``data.company_profiles`` if the directory is missing.

Damodaran shifts URLs and column names year over year — every fetch is
wrapped in try/except so a broken URL only loses that dataset, not the
whole run.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import requests


_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data" / "damodaran"

# URLs as of Jan 2025 — the file naming has been stable for several years
# but verify before each annual refresh.
DAMODARAN_URLS: dict[str, str] = {
    "betas":       "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls",
    "wacc":        "https://pages.stern.nyu.edu/~adamodar/pc/datasets/wacc.xls",
    "margins":     "https://pages.stern.nyu.edu/~adamodar/pc/datasets/margin.xls",
    "roic":        "https://pages.stern.nyu.edu/~adamodar/pc/datasets/roe.xls",
    "multiples":   "https://pages.stern.nyu.edu/~adamodar/pc/datasets/pedata.xls",
    "ev_multiples": "https://pages.stern.nyu.edu/~adamodar/pc/datasets/vebitda.xls",
    "dividends":   "https://pages.stern.nyu.edu/~adamodar/pc/datasets/divfund.xls",
    "debt":        "https://pages.stern.nyu.edu/~adamodar/pc/datasets/dbtfund.xls",
    "capex":       "https://pages.stern.nyu.edu/~adamodar/pc/datasets/capex.xls",
}


def _download(name: str, url: str) -> None:
    """Pull a single Excel file and persist it as parquet."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        print(f"  ✗ {name:<14}  fetch failed: {exc}")
        return

    # Damodaran usually starts the table around row 7; we try a few skiprows
    # so the script doesn't break if he moves the header.
    df: pd.DataFrame | None = None
    last_err: Exception | None = None
    for skip in (7, 6, 8, 5, 9, 0):
        try:
            df_attempt = pd.read_excel(r.content, sheet_name=0, skiprows=skip)
            # Validate: needs an industry column AND at least 10 rows
            cols = [str(c).strip() for c in df_attempt.columns]
            if any(c.lower().startswith("industry") for c in cols) and len(df_attempt) >= 10:
                df = df_attempt
                break
        except Exception as exc:
            last_err = exc
            continue
    if df is None:
        print(f"  ✗ {name:<14}  parse failed: {last_err}")
        return

    out = _DATA_DIR / f"{name}.parquet"
    df.to_parquet(out)
    print(f"  ✔ {name:<14}  {len(df):>4} industries  →  {out.relative_to(_PROJECT_ROOT)}")


def main() -> int:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Damodaran ingestion → {_DATA_DIR.relative_to(_PROJECT_ROOT)}")
    for name, url in DAMODARAN_URLS.items():
        _download(name, url)
    print("Done. Parquet files in data/damodaran/ — re-run annually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
