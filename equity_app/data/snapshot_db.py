"""
Auto-snapshot of the analysis state every time a ticker is opened.

Each snapshot is keyed by a hash of the income statement so dupes are
silently dropped (re-opening AAPL twice in a day produces ONE snapshot,
not two). When SEC EDGAR ships a restatement, the income hash changes
and a new snapshot is recorded — the diff helper highlights what moved.

Storage: SQLite under ``data/snapshots.db``. Lightweight, no external
dependencies.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


# ============================================================
# Internals
# ============================================================
def _db_path() -> Path:
    p = Path("data/snapshots.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            captured_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            price           REAL,
            intrinsic       REAL,
            implied_growth  REAL,
            financials_hash TEXT,
            payload         TEXT NOT NULL,
            UNIQUE(ticker, financials_hash)
        );
        CREATE INDEX IF NOT EXISTS ix_snap_ticker ON snapshots(ticker);
        """)


def _financials_hash(income: Optional[pd.DataFrame]) -> str:
    if income is None or income.empty:
        return "empty"
    try:
        return str(int(pd.util.hash_pandas_object(income, index=True).sum()))
    except Exception:
        return f"shape_{income.shape}"


def _df_to_dict(df: Optional[pd.DataFrame]) -> dict:
    if df is None or df.empty:
        return {}
    out: dict = {}
    for col in df.columns:
        out[col] = {str(idx): (None if pd.isna(v) else float(v))
                    for idx, v in df[col].items()
                    if isinstance(v, (int, float)) or pd.isna(v)}
    return out


def _info_clean(info: Any) -> dict:
    if not isinstance(info, dict):
        return {}
    return {
        k: v for k, v in info.items()
        if isinstance(v, (str, int, float, bool, type(None)))
    }


# ============================================================
# Public API
# ============================================================
def save_snapshot(
    ticker: str,
    bundle,
    *,
    intrinsic: Optional[float] = None,
    implied_growth: Optional[float] = None,
) -> Optional[int]:
    """Record a snapshot. Returns the new row id, or ``None`` if a row
    with the same financials_hash already exists (dedupe semantics).

    The function is best-effort: any DB / serialization error is
    swallowed so callers can wire it as a fire-and-forget side effect.
    """
    try:
        init_db()
        income = getattr(bundle, "income", None)
        balance = getattr(bundle, "balance", None)
        cash = getattr(bundle, "cash", None)
        info = getattr(bundle, "info", {}) or {}
        quote = getattr(bundle, "quote", {}) or {}

        fin_hash = _financials_hash(income)
        payload = {
            "info":    _info_clean(info),
            "income":  _df_to_dict(income),
            "balance": _df_to_dict(balance),
            "cash":    _df_to_dict(cash),
        }
        with _connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO snapshots (
                        ticker, price, intrinsic, implied_growth,
                        financials_hash, payload
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticker.upper(),
                        quote.get("price"),
                        intrinsic, implied_growth,
                        fin_hash,
                        json.dumps(payload, default=str),
                    ),
                )
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None
    except Exception:
        return None


def list_snapshots(ticker: str, limit: int = 30) -> list[dict]:
    """Most-recent-first listing for one ticker."""
    try:
        init_db()
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, captured_at, price, intrinsic,
                       implied_growth, financials_hash
                FROM snapshots WHERE ticker=?
                ORDER BY captured_at DESC LIMIT ?
                """,
                (ticker.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_snapshot(snap_id: int) -> Optional[dict]:
    try:
        init_db()
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id=?", (snap_id,),
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    out = dict(row)
    try:
        out["payload"] = json.loads(out["payload"])
    except Exception:
        out["payload"] = {}
    return out


def restatement_diff(
    current_income: pd.DataFrame,
    old_payload: dict,
    *,
    threshold_pct: float = 0.5,
) -> Optional[pd.DataFrame]:
    """Compare a current income statement against an old snapshot's
    payload['income'] and return rows where revenue moved >threshold%.

    Returns ``None`` when nothing material changed (caller renders empty).
    """
    if current_income is None or current_income.empty:
        return None
    old_income_dict = (old_payload or {}).get("income", {})
    if "revenue" not in old_income_dict or "revenue" not in current_income.columns:
        return None
    old_rev = pd.Series({pd.Timestamp(k): v
                         for k, v in old_income_dict["revenue"].items()
                         if v is not None})
    cur_rev = current_income["revenue"]
    common = old_rev.index.intersection(cur_rev.index)
    if len(common) == 0:
        return None
    df = pd.DataFrame({
        "Then": old_rev.loc[common],
        "Now":  cur_rev.loc[common],
    })
    df["% Δ"] = (df["Now"] - df["Then"]) / df["Then"].replace(0, pd.NA) * 100.0
    moved = df[df["% Δ"].abs() > threshold_pct]
    return moved if not moved.empty else None
